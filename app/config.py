from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    GEMINI_API_KEY: str = Field(min_length=1)

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    upload_dir: str = Field(default="./uploads", min_length=1)
    max_file_size: int = Field(default=10 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=500, ge=1, le=10_000)
    max_pdf_chars: int = Field(default=500_000, ge=1, le=10_000_000)

    auth_requests_per_minute: int = Field(default=30, ge=1, le=100_000)
    upload_requests_per_minute: int = Field(default=8, ge=1, le=100_000)
    chat_requests_per_minute: int = Field(default=20, ge=1, le=100_000)
    default_requests_per_minute: int = Field(default=120, ge=1, le=100_000)
    max_rate_limit_keys: int = Field(default=10_000, ge=100, le=1_000_000)

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
