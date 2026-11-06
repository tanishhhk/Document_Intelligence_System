from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


KNOWN_PROVIDERS = {"ollama", "openrouter", "groq", "gemini"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(min_length=1)
    secret_key: str = Field(min_length=32)
    algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)

    # Answer providers are tried in this order. Providers without credentials
    # (or, for Ollama, without a model) are skipped.
    llm_providers: str = Field(default="ollama,openrouter,groq,gemini", max_length=200)
    llm_timeout_seconds: float = Field(default=20.0, ge=1, le=120)
    llm_max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    llm_max_concurrent_requests: int = Field(default=8, ge=1, le=256)
    # When every provider fails: "extractive" returns the best-matching
    # passages, clearly labelled as not generated; "none" returns an error.
    answer_fallback: Literal["extractive", "none"] = "extractive"

    ollama_base_url: str = Field(default="http://localhost:11434/v1", max_length=500)
    ollama_model: str = Field(default="", max_length=200)

    openrouter_api_key: str = ""
    # Comma-separated; OpenRouter falls back through them in order.
    openrouter_model: str = Field(default="openrouter/free", min_length=1, max_length=500)

    groq_api_key: str = ""
    groq_model: str = Field(default="openai/gpt-oss-120b", min_length=1, max_length=200)

    GEMINI_API_KEY: str = ""
    gemini_model: str = Field(default="gemini-3.8-flash", min_length=1, max_length=100)
    # gemini-3.8-flash accepts low, medium and high. Use model-default for
    # models that do not support thinking levels.
    gemini_thinking_level: Literal["low", "medium", "high", "model-default"] = "low"

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    auto_migrate: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    ingestion_worker_enabled: bool = True

    upload_dir: str = Field(default="./uploads", min_length=1)
    max_file_size: int = Field(default=10 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=100, ge=1, le=10_000)
    max_pdf_chars: int = Field(default=300_000, ge=1, le=10_000_000)
    max_documents_per_user: int = Field(default=20, ge=1, le=100_000)
    # Daily per-user limits, reset at midnight UTC. Free model quotas are shared by everyone.
    daily_uploads_per_user: int = Field(default=5, ge=0, le=1_000_000)
    daily_questions_per_user: int = Field(default=25, ge=0, le=1_000_000)
    daily_stories_per_user: int = Field(default=3, ge=0, le=1_000_000)
    # PDFs are parsed in a child process that is stopped after this long, and
    # on Linux cannot use more than this much memory.
    pdf_parse_timeout_seconds: float = Field(default=60.0, ge=1, le=600)
    pdf_parse_memory_mb: int = Field(default=1024, ge=128, le=16_384)

    # Document stories. The text story is always produced; the narrated video
    # is rendered when enabled, in a child process with these limits.
    video_dir: str = Field(default="./generated_videos", min_length=1)
    video_render_enabled: bool = True
    video_render_timeout_seconds: float = Field(default=900.0, ge=30, le=3600)
    video_render_memory_mb: int = Field(default=2048, ge=256, le=16_384)
    # Older videos are deleted beyond this many per user; their stories stay.
    videos_kept_per_user: int = Field(default=3, ge=1, le=100)
    tts_voice: str = Field(default="en-US-AriaNeural", pattern=r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$")
    # Stories are written in the background, so a slow free model may take longer.
    story_timeout_seconds: float = Field(default=90.0, ge=5, le=600)
    # Reorder retrieved passages with a small cross-encoder (see app.services.reranker).
    reranker_enabled: bool = True
    # How much document text one story is written from.
    story_source_chars: int = Field(default=12_000, ge=1_000, le=200_000)

    auth_requests_per_minute: int = Field(default=30, ge=1, le=100_000)
    upload_requests_per_minute: int = Field(default=8, ge=1, le=100_000)
    chat_requests_per_minute: int = Field(default=20, ge=1, le=100_000)
    video_requests_per_minute: int = Field(default=3, ge=1, le=100_000)
    default_requests_per_minute: int = Field(default=120, ge=1, le=100_000)
    max_rate_limit_keys: int = Field(default=10_000, ge=100, le=1_000_000)

    @field_validator("database_url")
    @classmethod
    def use_installed_postgres_driver(cls, value: str) -> str:
        # Hosts such as Render hand out postgres:// or postgresql:// URLs, which
        # SQLAlchemy maps to psycopg2; the installed driver is psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @field_validator("llm_providers")
    @classmethod
    def validate_llm_providers(cls, value: str) -> str:
        names = [name.strip().lower() for name in value.split(",") if name.strip()]
        unknown = sorted(set(names) - KNOWN_PROVIDERS)
        if unknown:
            raise ValueError(f"Unknown answer providers: {', '.join(unknown)}.")
        return ",".join(dict.fromkeys(names))

    @property
    def llm_provider_order(self) -> list[str]:
        return [name for name in self.llm_providers.split(",") if name]

    @property
    def openrouter_models(self) -> list[str]:
        return [m.strip() for m in self.openrouter_model.split(",") if m.strip()]

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("At least one CORS origin must be configured.")

        normalized = []
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                not origin
                or origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS origins must be explicit HTTP or HTTPS origins without paths.")
            normalized.append(origin.rstrip("/"))

        return list(dict.fromkeys(normalized))


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
