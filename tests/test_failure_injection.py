"""Break dependencies on purpose and check the service fails safely and recovers."""
import errno
import os
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import documents as documents_api
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.document import Document
from app.models.upload_idempotency import UploadIdempotency
from app.services import ingestion
from tests.fakes import indexed

PDF = b"%PDF-1.7\ncontent"


def _upload(client, headers, key=None):
    return client.post(
        "/documents/upload",
        headers={**headers, "Idempotency-Key": key or f"fail-{uuid.uuid4().hex}"},
        files={"file": ("a.pdf", PDF, "application/pdf")},
    )


def _rows(factory, model):
    with factory() as db:
        return db.query(model).count()


def _files():
    folder = Path(settings.upload_dir)
    return list(folder.glob("*.pdf")) if folder.exists() else []


class BrokenSession:
    """Stands in for a session when the database connection has gone away."""

    def __getattr__(self, _name):
        def fail(*_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))

        return fail

    def close(self):
        pass


def test_a_database_outage_returns_a_generic_error_without_internals(db_session_factory, auth_headers):
    _user_id, headers = auth_headers

    def broken_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    response = TestClient(app, raise_server_exceptions=False).get("/documents", headers=headers)
    assert response.status_code == 500
    for leak in ("OperationalError", "SELECT", "Traceback", "server closed"):
        assert leak not in response.text


def test_a_full_disk_during_upload_leaves_nothing_behind(db_session_factory, auth_headers, monkeypatch):
    _user_id, headers = auth_headers

    async def disk_full(_file, path):
        Path(path).write_bytes(b"%PDF-partial")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(documents_api, "_save_upload", disk_full)
    response = _upload(TestClient(app, raise_server_exceptions=False), headers, "disk-full-upload-01")

    assert response.status_code == 500
    assert "No space" not in response.text
    assert _files() == []
    assert _rows(db_session_factory, Document) == 0
    assert _rows(db_session_factory, UploadIdempotency) == 0


def test_an_unwritable_upload_folder_is_reported_and_retry_works_afterwards(db_session_factory, auth_headers, monkeypatch):
    _user_id, headers = auth_headers
    original_mkdir = Path.mkdir

    def denied(self, *args, **kwargs):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", denied)
    client = TestClient(app, raise_server_exceptions=False)
    assert _upload(client, headers, "unwritable-folder-01").status_code == 500

    monkeypatch.setattr(Path, "mkdir", original_mkdir)
    assert _upload(client, headers, "unwritable-folder-01").status_code == 201


def test_a_failure_after_the_commit_is_safe_to_retry_with_the_same_key(db_session_factory, auth_headers, monkeypatch):
    _user_id, headers = auth_headers
    real_wake = documents_api._wake_worker
    calls = []

    def fail_after_commit(request):
        calls.append(1)
        raise OperationalError("SELECT", {}, Exception("connection reset"))

    # Fail after the document is committed, as a dropped connection would.
    # The client sees an error, and retrying with the same key returns the
    # stored document instead of creating a second one.
    monkeypatch.setattr(documents_api, "_wake_worker", fail_after_commit)
    response = _upload(TestClient(app, raise_server_exceptions=False), headers, "commit-then-fail-1")
    monkeypatch.setattr(documents_api, "_wake_worker", real_wake)

    assert response.status_code == 500 and calls
    replay = _upload(TestClient(app), headers, "commit-then-fail-1")
    assert replay.status_code == 201
    assert _rows(db_session_factory, Document) == 1


def test_the_worker_survives_a_database_outage(db_session_factory, monkeypatch):
    calls = []
    recovered = threading.Event()

    def flaky(session_factory, limit=None):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("SELECT", {}, Exception("database is restarting"))
        recovered.set()
        return 0

    monkeypatch.setattr(ingestion, "process_pending", flaky)
    monkeypatch.setattr(ingestion, "remove_orphan_files", lambda *a, **k: 0)
    monkeypatch.setattr(ingestion, "POLL_SECONDS", 0.05)
    worker = ingestion.IngestionWorker(db_session_factory, settings.upload_dir)
    worker.start()
    try:
        assert recovered.wait(5)
        assert worker.is_alive()
    finally:
        worker.stop(5)
    assert not worker.is_alive()


def test_a_crashing_parser_fails_only_that_document(db_session_factory, auth_headers, monkeypatch):
    _user_id, headers = auth_headers
    client = TestClient(app)
    bad = _upload(client, headers).json()
    good = _upload(client, headers).json()

    def parse(data):
        if parse.calls == 0:
            parse.calls += 1
            raise ingestion.DocumentRejected("Reading the PDF needed too much memory.")
        return indexed("Fine passage")

    parse.calls = 0
    monkeypatch.setattr(ingestion, "extract_and_embed_pdf", parse)
    ingestion.process_pending(db_session_factory)

    statuses = {d["id"]: d["status"] for d in client.get("/documents", headers=headers).json()["items"]}
    assert statuses == {bad["id"]: "failed", good["id"]: "completed"}


def test_a_document_whose_file_vanished_fails_with_a_reason(db_session_factory, auth_headers):
    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers).json()
    for path in _files():
        path.unlink()
    ingestion.process_pending(db_session_factory)
    document = client.get(f"/documents/{created['id']}", headers=headers).json()
    assert document["status"] == "failed"
    assert "no longer available" in document["error_message"]


def test_orphan_cleanup_continues_past_files_it_cannot_delete(db_session_factory, monkeypatch, tmp_path):
    folder = tmp_path / "orphans"
    folder.mkdir()
    paths = [folder / f"{uuid.uuid4()}.pdf" for _ in range(3)]
    old = time.time() - 7200
    for path in paths:
        path.write_bytes(PDF)
        os.utime(path, (old, old))

    real_unlink = Path.unlink
    locked = paths[0]

    def unlink(self, *args, **kwargs):
        if self == locked:
            raise PermissionError(errno.EACCES, "in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    assert ingestion.remove_orphan_files(db_session_factory, str(folder)) == 2
    assert locked.exists()


def test_a_stalled_provider_does_not_hang_the_request(db_session_factory, auth_headers, monkeypatch):
    """A provider that never answers is cut off by the deadline and the fallback is returned."""
    from app.api import chat as chat_api
    from app.services import llm
    from app.services.llm_providers import ProviderFailure
    from tests.fakes import vector

    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers).json()
    monkeypatch.setattr(ingestion, "extract_and_embed_pdf", lambda data: indexed("The fee is 30 euros."))
    ingestion.process_pending(db_session_factory)

    class Stalled:
        name, model = "stalled", "m"

        def generate(self, *_args):
            raise ProviderFailure("timeout", True)

    monkeypatch.setattr(llm, "_providers_cache", [Stalled()])
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    monkeypatch.setattr(chat_api, "generate_single_embedding", lambda _q: vector(0))
    monkeypatch.setattr(chat_api.settings, "answer_fallback", "extractive")

    started = time.monotonic()
    response = client.post("/chat/ask", headers=headers, json={"question": "Fee?", "document_id": created["id"]})
    assert response.status_code == 200
    assert response.json()["metadata"]["fallback_reason"] == "timeout"
    assert time.monotonic() - started < 10


@pytest.mark.parametrize("worker_enabled", [True, False])
def test_shutdown_stops_the_worker_and_releases_connections(db_session_factory, monkeypatch, worker_enabled):
    from app import main as main_module

    monkeypatch.setattr(settings, "ingestion_worker_enabled", worker_enabled)
    monkeypatch.setattr(main_module, "SessionLocal", db_session_factory)
    disposed = []
    monkeypatch.setattr(main_module.engine, "dispose", lambda: disposed.append(1))
    with TestClient(app):
        worker = app.state.ingestion_worker
        assert (worker is not None and worker.is_alive()) == worker_enabled
    assert disposed == [1]
    if worker_enabled:
        assert not worker.is_alive()
