"""OpenRouter, Groq and Ollama, tested against a mocked HTTP server."""
import json
import logging

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.llm_providers import OpenAICompatibleProvider, ProviderFailure, build_providers


def _provider(handler, models=("free/model",), api_key="sk-test"):
    return OpenAICompatibleProvider(
        "openrouter",
        "https://example.test/api/v1/",
        list(models),
        api_key=api_key,
        max_output_tokens=300,
        transport=httpx.MockTransport(handler),
    )


def _completion(content="Answer [S1].", finish="stop"):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}]}


def test_requests_use_the_chat_completions_format():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion())

    assert _provider(handler).generate("RULES", "<source>text</source>") == "Answer [S1]."
    assert seen["url"] == "https://example.test/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    body = seen["body"]
    assert body["model"] == "free/model"
    assert body["max_tokens"] == 300
    assert body["messages"] == [
        {"role": "system", "content": "RULES"},
        {"role": "user", "content": "<source>text</source>"},
    ]
    assert "models" not in body


def test_several_models_are_sent_as_an_ordered_fallback_list():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion())

    _provider(handler, models=("nvidia/nemotron:free", "openrouter/free")).generate("RULES", "q")
    assert seen["body"]["model"] == "nvidia/nemotron:free"
    assert seen["body"]["models"] == ["nvidia/nemotron:free", "openrouter/free"]


def test_local_servers_get_no_authorization_header():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_completion())

    _provider(handler, api_key="").generate("RULES", "q")
    assert seen["auth"] is None


@pytest.mark.parametrize(
    "status, headers, kind, retryable, retry_after",
    [
        (429, {"Retry-After": "7"}, "busy", True, 7.0),
        (429, {"Retry-After": "soon"}, "busy", True, None),
        (402, {}, "busy", False, None),
        (401, {}, "misconfigured", False, None),
        (403, {}, "misconfigured", False, None),
        (404, {}, "misconfigured", False, None),
        (400, {}, "rejected", False, None),
        (422, {}, "rejected", False, None),
        (408, {}, "timeout", True, None),
        (504, {}, "timeout", True, None),
        (500, {}, "unavailable", True, None),
        (502, {}, "unavailable", True, None),
        (503, {"Retry-After": "2"}, "unavailable", True, 2.0),
    ],
)
def test_http_errors_are_classified(status, headers, kind, retryable, retry_after):
    provider = _provider(lambda request: httpx.Response(status, headers=headers, json={"error": {}}))
    with pytest.raises(ProviderFailure) as raised:
        provider.generate("RULES", "q")
    failure = raised.value
    assert (failure.kind, failure.retryable, failure.retry_after, failure.status) == (
        kind, retryable, retry_after, status
    )


@pytest.mark.parametrize(
    "error, kind",
    [(httpx.ReadTimeout("slow"), "timeout"), (httpx.ConnectError("refused"), "unavailable")],
)
def test_network_errors_are_retryable(error, kind):
    def handler(request):
        raise error

    with pytest.raises(ProviderFailure) as raised:
        _provider(handler).generate("RULES", "q")
    assert (raised.value.kind, raised.value.retryable) == (kind, True)


@pytest.mark.parametrize(
    "response, kind",
    [
        (httpx.Response(200, content=b"<html>gateway error</html>"), "unavailable"),
        (httpx.Response(200, json={"error": {"code": 429, "message": "rate limited upstream"}}), "busy"),
        (httpx.Response(200, json={"error": {"message": "upstream failed"}}), "unavailable"),
        (httpx.Response(200, json={"choices": []}), "empty"),
        (httpx.Response(200, json={"choices": "nope"}), "empty"),
        (httpx.Response(200, json=[]), "empty"),
        (httpx.Response(200, json=_completion(content=None)), "empty"),
        (httpx.Response(200, json=_completion(content="   ")), "empty"),
        (httpx.Response(200, json={"choices": [{"finish_reason": "stop"}]}), "empty"),
        (httpx.Response(200, json=_completion(finish="content_filter")), "rejected"),
    ],
    ids=["not-json", "error-in-200", "error-without-code", "no-choices", "choices-not-list",
         "body-is-list", "null-content", "blank-content", "no-message", "content-filter"],
)
def test_malformed_and_empty_responses_are_failures(response, kind):
    with pytest.raises(ProviderFailure) as raised:
        _provider(lambda request: response).generate("RULES", "q")
    assert raised.value.kind == kind


def test_content_given_as_parts_is_joined():
    parts = [{"type": "text", "text": "The fee "}, {"type": "image_url"}, {"type": "text", "text": "is 30 [S1]."}]
    response = httpx.Response(200, json=_completion(content=parts))
    assert _provider(lambda request: response).generate("RULES", "q") == "The fee is 30 [S1]."


def test_truncated_answers_are_kept_and_logged(caplog):
    response = httpx.Response(200, json=_completion(content="The fee is", finish="length"))
    with caplog.at_level(logging.WARNING):
        assert _provider(lambda request: response).generate("RULES", "q") == "The fee is"
    assert "output token limit" in caplog.text


def test_overlong_answers_are_cut_to_the_limit():
    response = httpx.Response(200, json=_completion(content="x" * 50_000))
    assert len(_provider(lambda request: response).generate("RULES", "q")) == 8000


# Configuration


def _settings(**values):
    base = {"database_url": "sqlite://", "secret_key": "s" * 64}
    return Settings(_env_file=None, **{**base, **values})


def test_only_providers_with_credentials_are_used_in_the_configured_order():
    settings = _settings(
        llm_providers="gemini,groq,openrouter,ollama",
        GEMINI_API_KEY="g",
        groq_api_key="",
        openrouter_api_key="o",
        openrouter_model="a/b:free, openrouter/free",
        ollama_model="",
    )
    providers = build_providers(settings)
    assert [p.name for p in providers] == ["gemini", "openrouter"]
    assert providers[1].models == ["a/b:free", "openrouter/free"]


def test_ollama_is_enabled_by_choosing_a_model():
    providers = build_providers(_settings(ollama_model="qwen3:8b", GEMINI_API_KEY=""))
    assert [(p.name, p.model) for p in providers] == [("ollama", "qwen3:8b")]


def test_nothing_is_configured_by_default():
    assert build_providers(_settings(GEMINI_API_KEY="")) == []


def test_provider_names_are_validated_and_deduplicated():
    assert _settings(llm_providers=" Groq, groq ,gemini").llm_provider_order == ["groq", "gemini"]
    with pytest.raises(ValidationError):
        _settings(llm_providers="groq,chatgpt-free")
