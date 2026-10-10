from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    GEMINI_API_KEY: str

    upload_dir: str = "./uploads"
    max_file_size: int = 10 * 1024 * 1024
    max_pdf_pages: int = 500
    max_pdf_chars: int = 500_000

    auth_requests_per_minute: int = 30
    upload_requests_per_minute: int = 8
    chat_requests_per_minute: int = 20
    default_requests_per_minute: int = 120

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
