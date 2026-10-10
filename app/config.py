from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./document_intelligence.db"
    secret_key: str = Field(min_length=32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)

    GEMINI_API_KEY: str = Field(min_length=1)
    gemini_model: str = "gemini-3.8-flash"

    upload_dir: str = "./uploads"
    max_file_size: int = Field(default=10 * 1024 * 1024, gt=0)

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
