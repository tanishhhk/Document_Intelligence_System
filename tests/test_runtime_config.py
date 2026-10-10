import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.database import _engine_options


def make_settings(**overrides):
    values = {
        "database_url": "sqlite:///./test.db",
        "secret_key": "a" * 64,
        "GEMINI_API_KEY": "test-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_settings_reject_short_secret_keys():
    with pytest.raises(ValidationError):
        make_settings(secret_key="too-short")


def test_settings_reject_wildcard_cors_origin():
    with pytest.raises(ValidationError):
        make_settings(cors_origins=["*"])


def test_settings_reject_cors_origins_with_paths():
    with pytest.raises(ValidationError):
        make_settings(cors_origins=["https://example.com/app"])


def test_settings_normalize_and_deduplicate_cors_origins():
    settings = make_settings(
        cors_origins=["https://example.com/", "https://example.com"]
    )
    assert settings.cors_origins == ["https://example.com"]


def test_sqlite_receives_only_sqlite_connection_options():
    assert _engine_options("sqlite:///./test.db") == {
        "connect_args": {"check_same_thread": False}
    }


def test_postgres_does_not_receive_sqlite_connection_options():
    assert _engine_options("postgresql+psycopg://user:pass@localhost/app") == {}


def test_cors_middleware_rejects_unlisted_origins():
    from app.main import app

    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "https://not-allowed.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_allows_configured_origins():
    from app.main import app

    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_settings_do_not_allow_unexpected_jwt_algorithms():
    with pytest.raises(ValidationError):
        make_settings(algorithm="none")
