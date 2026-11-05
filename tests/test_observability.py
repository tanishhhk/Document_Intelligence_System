import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.logging_config import JsonFormatter, request_id_var
from app.main import app


@pytest.fixture()
def records(caplog):
    caplog.set_level(logging.INFO, logger="app.request")
    return caplog


def test_responses_carry_a_generated_request_id(records):
    response = TestClient(app).get("/health")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    entry = next(r for r in records.records if r.name == "app.request")
    assert entry.status_code == 200
    assert entry.path == "/health"
    assert entry.duration_ms >= 0


def test_a_safe_client_request_id_is_reused():
    response = TestClient(app).get("/health", headers={"X-Request-ID": "client-trace.42"})
    assert response.headers["X-Request-ID"] == "client-trace.42"


@pytest.mark.parametrize("supplied", ["has spaces", "x" * 65, "semi;colon", "<script>"])
def test_unsafe_client_request_ids_are_replaced(supplied):
    response = TestClient(app).get("/health", headers={"X-Request-ID": supplied})
    assert response.headers["X-Request-ID"] != supplied
    assert len(response.headers["X-Request-ID"]) == 32


def test_rejected_requests_also_get_a_request_id(auth_headers):
    _user_id, headers = auth_headers
    response = TestClient(app).post(
        "/chat/ask",
        headers={**headers, "Content-Length": str(5 * 1024 * 1024)},
        content=b"{}",
    )
    assert response.status_code == 413
    assert "X-Request-ID" in response.headers


def test_request_logs_do_not_contain_credentials_or_query_strings(records, auth_headers):
    _user_id, headers = auth_headers
    TestClient(app).get("/documents", headers=headers, params={"q": "salary review"})
    logged = " ".join(f"{r.getMessage()} {vars(r)}" for r in records.records)
    token = headers["Authorization"].split()[1]
    assert token not in logged
    assert "salary review" not in logged


def test_json_lines_include_extra_fields_and_the_request_id():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "Document processed.", None, None)
    record.document_id = "doc-1"
    record.chunk_count = 3
    token = request_id_var.set("req-123")
    try:
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["message"] == "Document processed."
    assert line["document_id"] == "doc-1"
    assert line["chunk_count"] == 3
    assert line["request_id"] == "req-123"
    assert line["level"] == "INFO"


def test_database_errors_do_not_expose_sql_parameters():
    from sqlalchemy import text

    from app.database import engine

    secret = f"private-chunk-text-{uuid.uuid4()}"
    with pytest.raises(Exception) as raised:
        with engine.connect() as connection:
            connection.execute(text("SELECT * FROM table_that_does_not_exist WHERE x = :v"), {"v": secret})
    assert secret not in str(raised.value)


def test_readiness_reports_an_unmigrated_database(monkeypatch):
    monkeypatch.setattr(main_module, "schema_is_current", lambda _connection: False)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["schema"] == "outdated"


def test_readiness_passes_when_the_database_is_current(monkeypatch):
    monkeypatch.setattr(main_module, "schema_is_current", lambda _connection: True)
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {
        "database": "ok",
        "schema": "current",
        "ingestion_worker": "disabled",
        "video_worker": "disabled",
        "video_rendering": "enabled",
        "answer_providers": "none",
    }


def test_readiness_fails_when_the_database_is_unreachable(monkeypatch):
    class Unreachable:
        def connect(self):
            raise OSError("connection refused")

    monkeypatch.setattr(main_module, "engine", Unreachable())
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"


def test_readiness_fails_when_the_enabled_worker_has_stopped(monkeypatch):
    monkeypatch.setattr(main_module, "schema_is_current", lambda _connection: True)
    monkeypatch.setattr(main_module.settings, "ingestion_worker_enabled", True)
    monkeypatch.setattr(app.state, "ingestion_worker", None, raising=False)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["ingestion_worker"] == "stopped"


def test_schema_check_compares_with_the_latest_migration(tmp_path):
    from alembic import command
    from sqlalchemy import create_engine

    from app.database import schema_is_current
    from tests.test_migrations import _alembic

    url = f"sqlite:///{(tmp_path / 'ready.db').as_posix()}"
    engine = create_engine(url)
    try:
        command.upgrade(_alembic(url), "0004")
        with engine.connect() as connection:
            assert schema_is_current(connection) is False
        command.upgrade(_alembic(url), "head")
        with engine.connect() as connection:
            assert schema_is_current(connection) is True
    finally:
        engine.dispose()
