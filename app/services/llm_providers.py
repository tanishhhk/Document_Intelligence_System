"""Answer generation backends.

Each provider turns a system instruction and a user message into answer
text, or raises ProviderFailure saying why it could not. Errors it does not
recognise propagate unchanged, so bugs are not disguised as outages.

OpenRouter, Groq and Ollama share the OpenAI chat completions format and
use OpenAICompatibleProvider; Gemini uses the Google GenAI SDK.
"""
import logging
import threading

import httpx

logger = logging.getLogger(__name__)

# Failure kinds, in the order the most useful one is reported when every
# provider fails: transient problems first, so clients know a retry may work.
FAILURE_PRIORITY = ["busy", "timeout", "unavailable", "empty", "rejected", "misconfigured"]

_MAX_ANSWER_CHARS = 8000


class ProviderFailure(Exception):
    def __init__(self, kind: str, retryable: bool, retry_after: float | None = None, status=None):
        super().__init__(kind)
        self.kind = kind
        self.retryable = retryable
        self.retry_after = retry_after
        self.status = status


def _retry_after_header(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after", "")
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _classify_status(status: int, retry_after: float | None) -> ProviderFailure:
    if status == 429:
        return ProviderFailure("busy", True, retry_after, status)
    if status == 402:  # OpenRouter: credits or free quota used up.
        return ProviderFailure("busy", False, retry_after, status)
    if status in (408, 504):
        return ProviderFailure("timeout", True, retry_after, status)
    if status >= 500:
        return ProviderFailure("unavailable", True, retry_after, status)
    if status in (401, 403, 404):
        return ProviderFailure("misconfigured", False, None, status)
    return ProviderFailure("rejected", False, None, status)


def _message_text(content) -> str:
    # Most servers return a string; some return a list of typed parts.
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


class OpenAICompatibleProvider:
    """A server implementing POST {base_url}/chat/completions."""

    def __init__(
        self,
        name: str,
        base_url: str,
        models: list[str],
        api_key: str = "",
        max_output_tokens: int = 1024,
        timeout_seconds: float = 20.0,
        extra_headers: dict | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = name
        self.models = models
        self.model = models[0]
        self.max_output_tokens = max_output_tokens
        headers = {"Content-Type": "application/json", **(extra_headers or {})}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def generate(self, system_instruction: str, user_message: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.max_output_tokens,
            "temperature": 0.2,
        }
        if len(self.models) > 1:
            # OpenRouter tries these in order when a model is unavailable.
            body["models"] = self.models
        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise ProviderFailure("timeout", True) from exc
        except httpx.TransportError as exc:
            raise ProviderFailure("unavailable", True) from exc

        if response.status_code != 200:
            raise _classify_status(response.status_code, _retry_after_header(response))
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderFailure("unavailable", False, status=200) from exc

        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            # Some gateways report upstream failures inside a 200 response.
            code = error.get("code")
            raise _classify_status(code if isinstance(code, int) else 502, None)

        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderFailure("empty", False)
        choice = choices[0]
        if choice.get("finish_reason") == "content_filter":
            raise ProviderFailure("rejected", False)
        if choice.get("finish_reason") == "length":
            logger.warning("Answer reached the output token limit.", extra={"provider": self.name})
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        text = _message_text(message.get("content")).strip()
        if not text:
            # A reasoning model can spend the whole output limit thinking and
            # return nothing. Another attempt, often routed to another free
            # model, usually answers.
            raise ProviderFailure("empty", choice.get("finish_reason") == "length")
        return text[:_MAX_ANSWER_CHARS]


class GeminiProvider:
    """Google Gemini through the google-genai SDK."""

    _BLOCKED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
    _RETRYABLE = {408, 429, 500, 502, 503, 504}

    def __init__(self, api_key, model, max_output_tokens, timeout_seconds, thinking_level):
        self.name = "gemini"
        self.model = model
        self._api_key = api_key
        self._max_output_tokens = max_output_tokens
        self._timeout_seconds = timeout_seconds
        self._thinking_level = thinking_level
        self._client = None
        self._lock = threading.Lock()

    def _create_client(self):
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=int(self._timeout_seconds * 1000)),
        )

    def _get_client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._create_client()
        return self._client

    def _config(self, system_instruction):
        from google.genai import types

        options = {
            "system_instruction": system_instruction,
            "max_output_tokens": self._max_output_tokens,
        }
        if self._thinking_level != "model-default":
            options["thinking_config"] = types.ThinkingConfig(
                thinking_level=self._thinking_level.upper()
            )
        return types.GenerateContentConfig(**options)

    @staticmethod
    def _error_details(exc) -> list[dict]:
        details = getattr(exc, "details", None)
        entries = details.get("error", {}).get("details", []) if isinstance(details, dict) else []
        return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []

    def _retry_delay(self, exc) -> float | None:
        """Read the delay from a google.rpc.RetryInfo detail, such as "7s"."""
        for entry in self._error_details(exc):
            if entry.get("@type", "").endswith("google.rpc.RetryInfo"):
                try:
                    return float(str(entry.get("retryDelay", "")).rstrip("s"))
                except ValueError:
                    return None
        return None

    def _classify(self, exc) -> ProviderFailure | None:
        from google.genai import errors

        if isinstance(exc, httpx.TimeoutException):
            return ProviderFailure("timeout", True)
        if isinstance(exc, httpx.TransportError):
            return ProviderFailure("unavailable", True)
        if not isinstance(exc, errors.APIError):
            return None
        code = exc.code
        # An invalid API key is reported as 400 with reason API_KEY_INVALID.
        reasons = {str(entry.get("reason", "")) for entry in self._error_details(exc)}
        if code in (401, 403, 404) or any(reason.startswith("API_KEY") for reason in reasons):
            return ProviderFailure("misconfigured", False, status=code)
        if code == 429:
            return ProviderFailure("busy", True, self._retry_delay(exc), code)
        if code in self._RETRYABLE:
            kind = "timeout" if code in (408, 504) else "unavailable"
            return ProviderFailure(kind, True, self._retry_delay(exc), code)
        return ProviderFailure("rejected", False, status=code)

    def generate(self, system_instruction: str, user_message: str) -> str:
        try:
            response = self._get_client().models.generate_content(
                model=self.model,
                contents=user_message,
                config=self._config(system_instruction),
            )
        except Exception as exc:
            failure = self._classify(exc)
            if failure is None:
                raise
            raise failure from exc

        candidates = getattr(response, "candidates", None) or []
        finish = getattr(candidates[0], "finish_reason", None) if candidates else None
        finish_name = getattr(finish, "name", finish)
        feedback = getattr(response, "prompt_feedback", None)
        if getattr(feedback, "block_reason", None) or finish_name in self._BLOCKED:
            raise ProviderFailure("rejected", False)
        if finish_name == "MAX_TOKENS":
            logger.warning("Answer reached the output token limit.", extra={"provider": self.name})
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ProviderFailure("empty", False)
        return text.strip()[:_MAX_ANSWER_CHARS]


def build_providers(
    settings,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
) -> list:
    """Configured providers in LLM_PROVIDER_ORDER, skipping any without credentials.

    timeout_seconds and max_output_tokens override the settings, for longer
    background generations such as stories.
    """
    timeout_seconds = timeout_seconds or settings.llm_timeout_seconds
    max_output_tokens = max_output_tokens or settings.llm_max_output_tokens
    common = {
        "max_output_tokens": max_output_tokens,
        "timeout_seconds": timeout_seconds,
        "transport": transport,
    }
    available = {}
    if settings.ollama_model:
        available["ollama"] = lambda: OpenAICompatibleProvider(
            "ollama", settings.ollama_base_url, [settings.ollama_model], **common
        )
    if settings.openrouter_api_key:
        available["openrouter"] = lambda: OpenAICompatibleProvider(
            "openrouter",
            "https://openrouter.ai/api/v1",
            settings.openrouter_models,
            api_key=settings.openrouter_api_key,
            extra_headers={"X-Title": "guruKool"},
            **common,
        )
    if settings.groq_api_key:
        available["groq"] = lambda: OpenAICompatibleProvider(
            "groq",
            "https://api.groq.com/openai/v1",
            [settings.groq_model],
            api_key=settings.groq_api_key,
            **common,
        )
    if settings.GEMINI_API_KEY:
        available["gemini"] = lambda: GeminiProvider(
            settings.GEMINI_API_KEY,
            settings.gemini_model,
            max_output_tokens,
            timeout_seconds,
            settings.gemini_thinking_level,
        )
    return [available[name]() for name in settings.llm_provider_order if name in available]
