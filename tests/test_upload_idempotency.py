import asyncio
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.services import ingestion
from app.config import settings
from app.main import app
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.models.document import Document
from app.models.upload_idempotency import UploadIdempotency
from tests.fakes import indexed

PDF_A = b"%PDF-1.7\nfirst document"
PDF_B = b"%PDF-1.7\nsecond, different document"


@pytest.fixture()
def ingest_calls(monkeypatch):
    calls = []

    def fake_extract(path):
        calls.append(path)
        return indexed("Example passage")

    monkeypatch.setattr(ingestion, "extract_and_embed_pdf", fake_extract)
    return calls


def _upload(client, headers, key, content=PDF_A):
    return client.post(
        "/documents/upload",
        headers={**headers, "Idempotency-Key": key},
        files={"file": ("report.pdf", content, "application/pdf")},
    )


def _count(factory, model):
    db = factory()
    try:
        return db.query(model).count()
    finally:
        db.close()


def _uploaded_files():
    from pathlib import Path

    folder = Path(settings.upload_dir)
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_same_key_and_same_file_returns_the_original_document(
    db_session_factory, auth_headers, ingest_calls
):
    _user_id, headers = auth_headers
    client = TestClient(app)
    first = _upload(client, headers, "replay-same-file-0001")
    second = _upload(client, headers, "replay-same-file-0001")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert _count(db_session_factory, Document) == 1
    assert _uploaded_files() == [f"{first.json()['id']}.pdf"]

    assert ingestion.process_pending(db_session_factory) == 1
    assert len(ingest_calls) == 1


def test_same_key_with_a_different_file_is_rejected(
    db_session_factory, auth_headers, ingest_calls
):
    _user_id, headers = auth_headers
    client = TestClient(app)
    first = _upload(client, headers, "replay-other-file-001", PDF_A)
    second = _upload(client, headers, "replay-other-file-001", PDF_B)

    assert first.status_code == 201
    assert second.status_code == 409
    assert "different file" in second.json()["detail"]
    assert _count(db_session_factory, Document) == 1
    assert _uploaded_files() == [f"{first.json()['id']}.pdf"]


def _pause_after_claim(monkeypatch, action):
    """Run action(claim) right after the upload claims its key."""
    original_claim = documents_api._claim_idempotency_key

    def claim_then_act(*args):
        claim, existing = original_claim(*args)
        if claim is not None:
            action(claim)
        return claim, existing

    monkeypatch.setattr(documents_api, "_claim_idempotency_key", claim_then_act)


def test_a_failure_after_claiming_releases_the_key_for_a_retry(
    db_session_factory, auth_headers, monkeypatch
):
    _user_id, headers = auth_headers
    real_document = documents_api.Document

    def failing_document(**_values):
        raise RuntimeError("database connection dropped")

    monkeypatch.setattr(documents_api, "Document", failing_document)
    client = TestClient(app)
    failed = _upload(client, headers, "retry-after-failure-1")
    monkeypatch.setattr(documents_api, "Document", real_document)
    retried = _upload(client, headers, "retry-after-failure-1")

    assert failed.status_code == 500
    assert retried.status_code == 201, retried.text
    assert _count(db_session_factory, Document) == 1
    assert len(_uploaded_files()) == 1


def test_a_key_that_is_still_processing_returns_a_conflict(
    db_session_factory, auth_headers, monkeypatch
):
    _user_id, headers = auth_headers
    claimed, release = threading.Event(), threading.Event()

    def hold(_claim):
        claimed.set()
        assert release.wait(10)

    _pause_after_claim(monkeypatch, hold)
    results = {}

    def first_request():
        results["first"] = _upload(TestClient(app), headers, "still-processing-0001")

    worker = threading.Thread(target=first_request)
    worker.start()
    try:
        assert claimed.wait(10)
        monkeypatch.undo()
        duplicate = _upload(TestClient(app), headers, "still-processing-0001")
    finally:
        release.set()
        worker.join(10)

    assert duplicate.status_code == 409
    assert "still being processed" in duplicate.json()["detail"]
    assert int(duplicate.headers["Retry-After"]) > 0
    assert results["first"].status_code == 201
    assert _count(db_session_factory, Document) == 1


def test_concurrent_duplicate_uploads_create_one_document(
    db_session_factory, auth_headers, monkeypatch
):
    _user_id, headers = auth_headers
    gate = threading.Barrier(2)
    original_claim = documents_api._claim_idempotency_key

    def synchronized_claim(*args):
        # Line both requests up just before the claim insert, then keep the
        # winner busy long enough for the other to see its claim.
        gate.wait(10)
        claim, existing = original_claim(*args)
        if claim is not None:
            time.sleep(0.3)
        return claim, existing

    monkeypatch.setattr(documents_api, "_claim_idempotency_key", synchronized_claim)
    responses = []

    def send():
        responses.append(_upload(TestClient(app), headers, "concurrent-upload-01"))

    threads = [threading.Thread(target=send) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)

    assert sorted(r.status_code for r in responses) == [201, 409]
    assert _count(db_session_factory, Document) == 1
    assert _count(db_session_factory, UploadIdempotency) == 1
    assert len(_uploaded_files()) == 1


def _insert_claim(factory, user_id, key, *, lease_expires_at, payload_sha256=None):
    db = factory()
    try:
        now = int(time.time())
        db.add(
            UploadIdempotency(
                id=str(uuid.uuid4()),
                user_id=user_id,
                idempotency_key=key,
                status="processing",
                payload_sha256=payload_sha256,
                lease_token=str(uuid.uuid4()),
                lease_expires_at=lease_expires_at,
                expires_at=now + 3600,
            )
        )
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("lease_offset", [-1, None], ids=["expired-lease", "legacy-without-lease"])
def test_a_stale_processing_claim_is_recovered(
    db_session_factory, auth_headers, ingest_calls, lease_offset
):
    user_id, headers = auth_headers
    lease = None if lease_offset is None else int(time.time()) + lease_offset
    _insert_claim(db_session_factory, user_id, "crashed-upload-key-01", lease_expires_at=lease)

    response = _upload(TestClient(app), headers, "crashed-upload-key-01")

    assert response.status_code == 201, response.text
    db = db_session_factory()
    try:
        claim = db.query(UploadIdempotency).one()
        assert claim.status == "completed"
        assert claim.document_id == response.json()["id"]
    finally:
        db.close()


def test_a_live_processing_claim_is_not_taken_over(db_session_factory, auth_headers, ingest_calls):
    user_id, headers = auth_headers
    _insert_claim(
        db_session_factory, user_id, "live-upload-key-0001", lease_expires_at=int(time.time()) + 600
    )
    response = _upload(TestClient(app), headers, "live-upload-key-0001")
    assert response.status_code == 409
    assert ingest_calls == []
    assert _uploaded_files() == []


def test_a_request_that_lost_its_lease_does_not_create_a_document(
    db_session_factory, auth_headers, monkeypatch
):
    _user_id, headers = auth_headers

    def lose_lease(_claim):
        db = db_session_factory()
        try:
            db.query(UploadIdempotency).update({UploadIdempotency.lease_token: "taken-over"})
            db.commit()
        finally:
            db.close()

    _pause_after_claim(monkeypatch, lose_lease)
    response = _upload(TestClient(app), headers, "lost-lease-upload-01")

    assert response.status_code == 409
    assert _count(db_session_factory, Document) == 0
    assert _count(db_session_factory, UploadIdempotency) == 1  # The new owner's claim stays.
    assert _uploaded_files() == []


def test_reusing_the_key_of_a_deleted_document_is_rejected(
    db_session_factory, auth_headers, ingest_calls
):
    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers, "deleted-document-key1")
    assert client.delete(f"/documents/{created.json()['id']}", headers=headers).status_code == 200

    reused = _upload(client, headers, "deleted-document-key1")
    assert reused.status_code == 409
    assert "deleted" in reused.json()["detail"]


def test_uploads_over_the_declared_size_limit_are_rejected_before_parsing(
    db_session_factory, auth_headers, ingest_calls, monkeypatch
):
    _user_id, headers = auth_headers
    monkeypatch.setattr(settings, "max_file_size", 1024)
    saves = []
    monkeypatch.setattr(documents_api, "_save_upload", lambda *a: saves.append(a))

    response = _upload(TestClient(app), headers, "oversized-upload-0001", b"%PDF-" + b"x" * 200_000)

    assert response.status_code == 413
    assert saves == []
    assert _uploaded_files() == []


def test_json_bodies_over_one_megabyte_are_rejected(db_session_factory, auth_headers):
    _user_id, headers = auth_headers
    response = TestClient(app).post(
        "/chat/ask",
        headers={**headers, "Content-Type": "application/json"},
        content=b'{"question": "' + b"q" * (2 * 1024 * 1024) + b'", "document_id": "x"}',
    )
    assert response.status_code == 413


def test_streamed_bodies_without_a_length_are_cut_off_at_the_limit():
    received = []

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            received.append(len(message.get("body", b"")))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    class Limits:
        max_file_size = 10

    middleware = BodySizeLimitMiddleware(downstream, Limits())
    chunks = iter([b"a" * 600_000, b"b" * 600_000, b"c" * 600_000])
    statuses = []

    async def receive():
        body = next(chunks, b"")
        return {"type": "http.request", "body": body, "more_body": bool(body)}

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    scope = {"type": "http", "method": "POST", "path": "/chat/ask", "headers": []}
    asyncio.run(middleware(scope, receive, send))

    assert statuses == [413]
    assert sum(received) <= 2 * 600_000
