"""Gemini provider error handling, and the provider chain that tries each in turn."""
import logging
import threading
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from app.services import llm
from app.services.llm_providers import GeminiProvider, ProviderFailure
from app.services.retrieval import RetrievedChunk

SOURCES = [RetrievedChunk("S1", 0, "The fee is 30 euros.", 1, 1, 0.9)]


# Gemini provider


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
    return (errors.ClientError if code < 500 else errors.ServerError)(code, payload)


def _gemini(outcome, thinking="low"):
    provider = GeminiProvider("key", "gemini-3.8-flash", 512, 20, thinking)
    calls = []

    class Models:
        def generate_content(self, *, model, contents, config):
            calls.append({"model": model, "contents": contents, "config": config})
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    provider._client = SimpleNamespace(models=Models())
    return provider, calls


def test_gemini_sends_instructions_separately_with_limits():
    provider, calls = _gemini(_ok())
    assert provider.generate("RULES", "<source>text</source>") == "The fee is 30 euros [S1]."
    config = calls[0]["config"]
    assert calls[0]["model"] == "gemini-3.8-flash"
    assert config.system_instruction == "RULES"
    assert config.max_output_tokens == 512
    assert config.thinking_config.thinking_level.value == "LOW"


def test_gemini_thinking_can_be_left_to_the_model():
    provider, calls = _gemini(_ok(), thinking="model-default")
    provider.generate("RULES", "question")
    assert calls[0]["config"].thinking_config is None


@pytest.mark.parametrize(
    "failure, kind, retryable, retry_after",
    [
        (_api_error(429, "RESOURCE_EXHAUSTED", retry_delay="3s"), "busy", True, 3.0),
        (_api_error(500, "INTERNAL"), "unavailable", True, None),
        (_api_error(503, "UNAVAILABLE"), "unavailable", True, None),
        (_api_error(504, "DEADLINE_EXCEEDED"), "timeout", True, None),
        (httpx.ReadTimeout("timed out"), "timeout", True, None),
        (httpx.ConnectError("refused"), "unavailable", True, None),
        # Shape of the real response for an invalid key.
        (_api_error(400, "INVALID_ARGUMENT", "API key not valid.", reason="API_KEY_INVALID"),
         "misconfigured", False, None),
        (_api_error(401, "UNAUTHENTICATED"), "misconfigured", False, None),
        (_api_error(403, "PERMISSION_DENIED"), "misconfigured", False, None),
        (_api_error(404, "NOT_FOUND"), "misconfigured", False, None),
        (_api_error(400, "INVALID_ARGUMENT", "Request contains an invalid argument."), "rejected", False, None),
    ],
    ids=["rate-limit", "internal", "unavailable", "deadline", "timeout", "network", "invalid-key",
         "unauthenticated", "forbidden", "unknown-model", "invalid-request"],
)
def test_gemini_failures_are_classified(failure, kind, retryable, retry_after):
    provider, _calls = _gemini(failure)
    with pytest.raises(ProviderFailure) as raised:
        provider.generate("RULES", "question")
    assert (raised.value.kind, raised.value.retryable, raised.value.retry_after) == (kind, retryable, retry_after)


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
def test_gemini_blocked_and_empty_responses_are_failures(response, kind):
    provider, _calls = _gemini(response)
    with pytest.raises(ProviderFailure) as raised:
        provider.generate("RULES", "question")
    assert raised.value.kind == kind


def test_gemini_answers_cut_off_by_the_token_limit_are_kept(caplog):
    provider, _calls = _gemini(_ok(text="The fee is 30", finish="MAX_TOKENS"))
    with caplog.at_level(logging.WARNING):
        assert provider.generate("RULES", "question") == "The fee is 30"
    assert "output token limit" in caplog.text


def test_gemini_unexpected_exceptions_propagate():
    provider, _calls = _gemini(KeyError("bug"))
    with pytest.raises(KeyError):
        provider.generate("RULES", "question")


def test_gemini_client_is_created_once_with_a_timeout(monkeypatch):
    created = []
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: created.append(kwargs) or object())
    provider = GeminiProvider("key", "gemini-3.8-flash", 512, 12.5, "low")
    assert provider._get_client() is provider._get_client()
    assert len(created) == 1
    assert created[0]["http_options"].timeout == 12500


# Provider chain


class ScriptedProvider:
    def __init__(self, name, *outcomes):
        self.name = name
        self.model = f"{name}-model"
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate(self, system_instruction, user_message):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture()
def chain(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)

    def use(*providers):
        monkeypatch.setattr(llm, "_providers_cache", list(providers))
        return sleeps

    return use


def test_the_first_working_provider_answers(chain):
    first, second = ScriptedProvider("ollama", "From Ollama [S1]."), ScriptedProvider("openrouter", "unused")
    chain(first, second)
    answer = llm.generate_answer("What is the fee?", SOURCES)
    assert answer == llm.Answer("From Ollama [S1].", "ollama", "ollama-model")
    assert second.calls == 0


def test_a_transient_failure_is_retried_on_the_same_provider(chain):
    provider = ScriptedProvider("groq", ProviderFailure("unavailable", True), "Answer [S1].")
    sleeps = chain(provider)
    assert llm.generate_answer("q", SOURCES).text == "Answer [S1]."
    assert provider.calls == 2
    assert len(sleeps) == 1 and 0 <= sleeps[0] <= llm._MAX_DELAY_SECONDS


def test_a_failing_provider_hands_over_to_the_next(chain):
    broken = ScriptedProvider("openrouter", ProviderFailure("misconfigured", False))
    exhausted = ScriptedProvider("groq", ProviderFailure("busy", True), ProviderFailure("busy", True))
    working = ScriptedProvider("gemini", "Gemini answer [S1].")
    chain(broken, exhausted, working)

    answer = llm.generate_answer("q", SOURCES)
    assert answer.provider == "gemini"
    assert (broken.calls, exhausted.calls, working.calls) == (1, 2, 1)


def test_when_every_provider_fails_the_most_actionable_reason_is_reported(chain):
    chain(
        ScriptedProvider("openrouter", ProviderFailure("misconfigured", False)),
        ScriptedProvider("groq", ProviderFailure("busy", False, retry_after=4.0)),
        ScriptedProvider("gemini", ProviderFailure("busy", False, retry_after=6.0)),
    )
    with pytest.raises(llm.AnswerServiceError) as raised:
        llm.generate_answer("q", SOURCES)
    assert raised.value.kind == "busy"
    assert raised.value.retry_after == 6.0


def test_no_configured_provider_is_a_configuration_error(chain):
    chain()
    with pytest.raises(llm.AnswerServiceError) as raised:
        llm.generate_answer("q", SOURCES)
    assert raised.value.kind == "misconfigured"


def test_provider_retry_delays_are_honoured_and_long_ones_skip_ahead(chain):
    slow = ScriptedProvider("openrouter", ProviderFailure("busy", True, retry_after=40.0))
    quick = ScriptedProvider("groq", ProviderFailure("busy", True, retry_after=3.0), "Answer [S1].")
    sleeps = chain(slow, quick)
    assert llm.generate_answer("q", SOURCES).provider == "groq"
    assert slow.calls == 1  # 40 s is longer than the cap, so move on instead of waiting.
    assert sleeps == [3.0]


def test_backoff_stays_within_the_cap(chain, monkeypatch):
    monkeypatch.setattr(llm.random, "uniform", lambda low, high: high)
    sleeps = chain(ScriptedProvider("groq", ProviderFailure("unavailable", True), ProviderFailure("unavailable", True)))
    with pytest.raises(llm.AnswerServiceError):
        llm.generate_answer("q", SOURCES)
    assert sleeps == [2.0]


def test_unexpected_exceptions_are_not_disguised_as_provider_failures(chain):
    chain(ScriptedProvider("groq", KeyError("bug in our code")), ScriptedProvider("gemini", "unused"))
    with pytest.raises(KeyError):
        llm.generate_answer("q", SOURCES)


def test_logs_do_not_contain_document_text(chain, caplog):
    secret = "Salary of the chief executive is 950,000 euros."
    chain(ScriptedProvider("groq", ProviderFailure("rejected", False, status=400)))
    with caplog.at_level(logging.DEBUG), pytest.raises(llm.AnswerServiceError):
        llm.generate_answer("What is the salary?", [RetrievedChunk("S1", 0, secret, 1, 1, 0.9)])
    assert "950,000" not in caplog.text


def test_concurrent_requests_beyond_the_limit_are_turned_away(chain, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    class Blocking:
        name, model = "groq", "groq-model"

        def generate(self, *_args):
            entered.set()
            release.wait(5)
            return "done"

    chain(Blocking())
    monkeypatch.setattr(llm, "_slots", threading.BoundedSemaphore(1))
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
