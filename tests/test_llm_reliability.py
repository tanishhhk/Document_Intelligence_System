import logging
import threading
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from app.services import llm
from app.services.retrieval import RetrievedChunk

SOURCES = [RetrievedChunk("S1", 0, "The fee is 30 euros.", 1, 1, 0.9)]


def _ok(text="The fee is 30 euros [S1].", finish="STOP"):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        prompt_feedback=None,
    )


def _api_error(code, status="", message="", retry_delay=None, reason=None):
    details = []
    if reason is not None:
        details.append({"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason})
    if retry_delay is not None:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay})
    payload = {"error": {"code": code, "status": status, "message": message, "details": details}}
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, payload)


@pytest.fixture()
def provider(monkeypatch):
    """A fake Gemini client that plays back a list of results or exceptions."""
    state = {"script": [], "calls": [], "sleeps": []}

    class Models:
        def generate_content(self, *, model, contents, config):
            state["calls"].append({"model": model, "contents": contents, "config": config})
            outcome = state["script"].pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    monkeypatch.setattr(llm, "_get_client", lambda: SimpleNamespace(models=Models()))
    monkeypatch.setattr(llm.time, "sleep", state["sleeps"].append)
    return state


def test_a_successful_answer_uses_the_configured_limits(provider, monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_max_output_tokens", 512)
    monkeypatch.setattr(llm.settings, "gemini_thinking_level", "low")
    provider["script"] = [_ok()]

    assert llm.generate_answer("What is the fee?", SOURCES) == "The fee is 30 euros [S1]."
    config = provider["calls"][0]["config"]
    assert config.max_output_tokens == 512
    assert config.thinking_config.thinking_level.value == "LOW"
    assert config.system_instruction == llm.SYSTEM_INSTRUCTION


def test_thinking_configuration_can_be_left_to_the_model(provider, monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_thinking_level", "model-default")
    provider["script"] = [_ok()]
    llm.generate_answer("What is the fee?", SOURCES)
    assert provider["calls"][0]["config"].thinking_config is None


@pytest.mark.parametrize(
    "failure",
    [
        _api_error(429, "RESOURCE_EXHAUSTED"),
        _api_error(500, "INTERNAL"),
        _api_error(503, "UNAVAILABLE"),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("connection refused"),
    ],
    ids=["rate-limit", "server-error", "unavailable", "timeout", "network"],
)
def test_transient_failures_are_retried(provider, failure):
    provider["script"] = [failure, _ok()]
    assert llm.generate_answer("What is the fee?", SOURCES).startswith("The fee")
    assert len(provider["calls"]) == 2
    assert len(provider["sleeps"]) == 1
    assert 0 <= provider["sleeps"][0] <= llm._MAX_DELAY_SECONDS


def test_retries_stop_after_the_attempt_limit(provider):
    provider["script"] = [_api_error(503, "UNAVAILABLE")] * llm._MAX_ATTEMPTS
    with pytest.raises(llm.AnswerServiceError) as raised:
        llm.generate_answer("What is the fee?", SOURCES)
    assert raised.value.kind == "unavailable"
    assert len(provider["calls"]) == llm._MAX_ATTEMPTS
    assert len(provider["sleeps"]) == llm._MAX_ATTEMPTS - 1


def test_backoff_grows_and_stays_within_the_cap(provider, monkeypatch):
    monkeypatch.setattr(llm.random, "uniform", lambda low, high: high)
    provider["script"] = [_api_error(500)] * llm._MAX_ATTEMPTS
    with pytest.raises(llm.AnswerServiceError):
        llm.generate_answer("What is the fee?", SOURCES)
    assert provider["sleeps"] == [2.0, 4.0]


def test_the_provider_retry_delay_is_honoured(provider):
    provider["script"] = [_api_error(429, "RESOURCE_EXHAUSTED", retry_delay="3s"), _ok()]
    llm.generate_answer("What is the fee?", SOURCES)
    assert provider["sleeps"] == [3.0]


def test_long_provider_delays_are_passed_back_instead_of_waited_out(provider):
    provider["script"] = [_api_error(429, "RESOURCE_EXHAUSTED", retry_delay="40s")]
    with pytest.raises(llm.AnswerServiceError) as raised:
        llm.generate_answer("What is the fee?", SOURCES)
    assert raised.value.kind == "busy"
    assert raised.value.retry_after == 40.0
    assert provider["sleeps"] == []


@pytest.mark.parametrize(
    "failure, kind",
    [
        # Shape of the real response for an invalid key.
        (
            _api_error(
                400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.",
                reason="API_KEY_INVALID",
            ),
            "misconfigured",
        ),
        (_api_error(401, "UNAUTHENTICATED"), "misconfigured"),
        (_api_error(403, "PERMISSION_DENIED"), "misconfigured"),
        (_api_error(404, "NOT_FOUND", "models/unknown is not found"), "misconfigured"),
        (_api_error(400, "INVALID_ARGUMENT", "Request contains an invalid argument."), "rejected"),
    ],
    ids=["invalid-key", "unauthenticated", "forbidden", "unknown-model", "invalid-request"],
)
def test_permanent_failures_are_not_retried(provider, failure, kind):
    provider["script"] = [failure]
    with pytest.raises(llm.AnswerServiceError) as raised:
        llm.generate_answer("What is the fee?", SOURCES)
    assert raised.value.kind == kind
    assert len(provider["calls"]) == 1
    assert provider["sleeps"] == []


@pytest.mark.parametrize(
    "response, kind",
    [
        (_ok(text=None, finish="SAFETY"), "rejected"),
        (SimpleNamespace(text=None, candidates=[], prompt_feedback=SimpleNamespace(block_reason="OTHER")), "rejected"),
        (_ok(text="   "), "empty"),
        (_ok(text=None), "empty"),
    ],
    ids=["safety-block", "prompt-blocked", "blank", "missing-text"],
)
def test_blocked_and_empty_responses_are_reported(provider, response, kind):
    provider["script"] = [response]
    with pytest.raises(llm.AnswerServiceError) as raised:
        llm.generate_answer("What is the fee?", SOURCES)
    assert raised.value.kind == kind


def test_answers_cut_off_by_the_token_limit_are_returned(provider, caplog):
    provider["script"] = [_ok(text="The fee is 30", finish="MAX_TOKENS")]
    with caplog.at_level(logging.WARNING):
        assert llm.generate_answer("What is the fee?", SOURCES) == "The fee is 30"
    assert "output token limit" in caplog.text


def test_overlong_answers_are_truncated(provider):
    provider["script"] = [_ok(text="x" * 20_000)]
    assert len(llm.generate_answer("What is the fee?", SOURCES)) == llm._MAX_ANSWER_CHARS


def test_unexpected_exceptions_are_not_disguised_as_provider_errors(provider):
    provider["script"] = [KeyError("bug in our code")]
    with pytest.raises(KeyError):
        llm.generate_answer("What is the fee?", SOURCES)


def test_logs_do_not_contain_document_text_or_provider_messages(provider, caplog):
    secret = "Salary of the chief executive is 950,000 euros."
    provider["script"] = [_api_error(400, "INVALID_ARGUMENT", f"Bad request near: {secret}")]
    sources = [RetrievedChunk("S1", 0, secret, 1, 1, 0.9)]
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(llm.AnswerServiceError):
            llm.generate_answer("What is the salary?", sources)
    assert "950,000" not in caplog.text
    assert "test-only-placeholder-key" not in caplog.text


def test_concurrent_requests_beyond_the_limit_are_turned_away(monkeypatch):
    monkeypatch.setattr(llm, "_slots", threading.BoundedSemaphore(1))
    entered, release = threading.Event(), threading.Event()

    def slow(_contents):
        entered.set()
        release.wait(5)
        return "done"

    monkeypatch.setattr(llm, "_generate", slow)
    worker = threading.Thread(target=llm.generate_answer, args=("q", SOURCES))
    worker.start()
    try:
        assert entered.wait(5)
        original_acquire = llm._slots.acquire
        monkeypatch.setattr(llm._slots, "acquire", lambda timeout: original_acquire(timeout=0.01))
        with pytest.raises(llm.AnswerServiceError) as raised:
            llm.generate_answer("q", SOURCES)
        assert raised.value.kind == "busy"
    finally:
        release.set()
        worker.join(5)


def test_the_client_is_created_once_with_a_timeout(monkeypatch):
    created = []
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm.settings, "gemini_timeout_seconds", 12.5)

    def fake_client(**kwargs):
        created.append(kwargs)
        return object()

    monkeypatch.setattr("google.genai.Client", fake_client)
    first, second = llm._get_client(), llm._get_client()
    assert first is second
    assert len(created) == 1
    assert created[0]["http_options"].timeout == 12500
