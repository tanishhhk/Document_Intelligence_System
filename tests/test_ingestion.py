import os
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.config import settings
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services import ingestion

PDF = b"%PDF-1.7\nquarterly report"


@pytest.fixture()
def extractor(monkeypatch):
    """Replace PDF parsing and embedding; tests choose the behavior per call."""
    state = {"calls": 0, "behavior": lambda data: (["First passage", "Second passage"], [[1.0, 0.0], [0.0, 1.0]])}

    def fake(data):
        state["calls"] += 1
        return state["behavior"](data)

    monkeypatch.setattr(ingestion, "extract_and_embed_pdf", fake)
    return state


def _upload(client, headers, key=None):
    response = client.post(
        "/documents/upload",
        headers={**headers, "Idempotency-Key": key or f"ingest-{uuid.uuid4().hex}"},
        files={"file": ("report.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _document(factory, document_id):
    with factory() as db:
        return db.get(Document, document_id)


def _chunks(factory, document_id):
    with factory() as db:
        return (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )


def _set(factory, document_id, **values):
    with factory() as db:
        db.query(Document).filter(Document.id == document_id).update(values)
        db.commit()


def test_upload_is_queued_and_processed_by_the_worker(db_session_factory, auth_headers, extractor):
    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers)

    assert created["status"] == "queued"
    assert extractor["calls"] == 0
    assert _chunks(db_session_factory, created["id"]) == []

    assert ingestion.process_pending(db_session_factory) == 1

    body = client.get(f"/documents/{created['id']}", headers=headers).json()
    assert body["status"] == "completed"
    assert body["chunk_count"] == 2
    assert body["processed_at"] is not None
    assert body["error_message"] is None
    assert [c.chunk_text for c in _chunks(db_session_factory, created["id"])] == [
        "First passage",
        "Second passage",
    ]


def test_questions_about_unprocessed_documents_get_a_clear_conflict(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers)
    response = client.post(
        "/chat/ask",
        headers=headers,
        json={"question": "What changed?", "document_id": created["id"]},
    )
    assert response.status_code == 409
    assert "still being processed" in response.json()["detail"]


def test_rejected_documents_fail_with_a_reason_and_can_be_retried(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers)

    def rejected(_data):
        raise ingestion.DocumentRejected("No selectable text was found. Scanned PDFs need OCR.")

    extractor["behavior"] = rejected
    ingestion.process_pending(db_session_factory)

    failed = client.get(f"/documents/{created['id']}", headers=headers).json()
    assert failed["status"] == "failed"
    assert "OCR" in failed["error_message"]
    assert extractor["calls"] == 1  # Rejections are not retried automatically.

    retried = client.post(f"/documents/{created['id']}/retry", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"

    extractor["behavior"] = lambda _data: (["Passage"], [[1.0, 0.0]])
    ingestion.process_pending(db_session_factory)
    assert _document(db_session_factory, created["id"]).status == "completed"


def test_unexpected_errors_are_retried_then_marked_failed(db_session_factory, auth_headers, extractor):
    _user_id, headers = auth_headers
    created = _upload(TestClient(app), headers)

    def broken(_data):
        raise RuntimeError("model weights could not be loaded")

    extractor["behavior"] = broken
    ingestion.process_pending(db_session_factory)

    document = _document(db_session_factory, created["id"])
    assert extractor["calls"] == ingestion.MAX_ATTEMPTS
    assert document.status == "failed"
    assert document.attempts == ingestion.MAX_ATTEMPTS
    assert "model weights" not in document.error_message  # Internal details stay in the logs.


def test_documents_abandoned_by_a_crashed_worker_are_processed_again(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    created = _upload(TestClient(app), headers)
    _set(
        db_session_factory,
        created["id"],
        status="processing",
        attempts=1,
        lease_token="dead-worker",
        lease_expires_at=int(time.time()) - 1,
    )

    assert ingestion.process_pending(db_session_factory) == 1
    document = _document(db_session_factory, created["id"])
    assert document.status == "completed"
    assert document.attempts == 2


def test_documents_with_a_live_lease_are_left_alone(db_session_factory, auth_headers, extractor):
    _user_id, headers = auth_headers
    created = _upload(TestClient(app), headers)
    _set(
        db_session_factory,
        created["id"],
        status="processing",
        attempts=1,
        lease_token="busy-worker",
        lease_expires_at=int(time.time()) + 600,
    )
    assert ingestion.process_pending(db_session_factory) == 0
    assert extractor["calls"] == 0


def test_files_that_keep_crashing_the_worker_are_not_parsed_again(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    created = _upload(TestClient(app), headers)
    _set(
        db_session_factory,
        created["id"],
        status="processing",
        attempts=ingestion.MAX_ATTEMPTS,
        lease_token="dead-worker",
        lease_expires_at=int(time.time()) - 1,
    )

    ingestion.process_pending(db_session_factory)
    document = _document(db_session_factory, created["id"])
    assert document.status == "failed"
    assert "stopped repeatedly" in document.error_message
    assert extractor["calls"] == 0


def test_a_worker_that_lost_its_lease_does_not_store_results(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    created = _upload(TestClient(app), headers)

    def lose_lease_while_working(_data):
        _set(db_session_factory, created["id"], lease_token="newer-worker")
        return ["Stale passage"], [[1.0, 0.0]]

    extractor["behavior"] = lose_lease_while_working
    ingestion.process_pending(db_session_factory, limit=1)

    document = _document(db_session_factory, created["id"])
    assert document.status == "processing"
    assert document.lease_token == "newer-worker"
    assert _chunks(db_session_factory, created["id"]) == []


def test_reprocessing_replaces_chunks_instead_of_duplicating_them(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    created = _upload(TestClient(app), headers)
    ingestion.process_pending(db_session_factory)
    _set(db_session_factory, created["id"], status="queued")

    extractor["behavior"] = lambda _data: (["Only passage"], [[1.0, 0.0]])
    ingestion.process_pending(db_session_factory)

    assert [c.chunk_text for c in _chunks(db_session_factory, created["id"])] == ["Only passage"]
    assert _document(db_session_factory, created["id"]).chunk_count == 1


def test_deleting_a_document_while_it_is_processed_leaves_nothing_behind(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers)

    def delete_mid_processing(_data):
        assert client.delete(f"/documents/{created['id']}", headers=headers).status_code == 200
        return ["Passage"], [[1.0, 0.0]]

    extractor["behavior"] = delete_mid_processing
    ingestion.process_pending(db_session_factory)

    assert _document(db_session_factory, created["id"]) is None
    assert _chunks(db_session_factory, created["id"]) == []
    assert list(Path(settings.upload_dir).glob("*.pdf")) == []


def test_only_one_of_several_workers_claims_a_document(db_session_factory, auth_headers, extractor):
    _user_id, headers = auth_headers
    _upload(TestClient(app), headers)
    gate = threading.Barrier(4)
    claims = []

    def claim():
        gate.wait(10)
        claims.append(ingestion.claim_next_document(db_session_factory))

    threads = [threading.Thread(target=claim) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)

    assert len([c for c in claims if c is not None]) == 1


def test_retry_is_limited_to_failed_documents_the_user_owns(
    db_session_factory, auth_headers, extractor
):
    _user_id, headers = auth_headers
    client = TestClient(app)
    created = _upload(client, headers)
    ingestion.process_pending(db_session_factory)

    completed = client.post(f"/documents/{created['id']}/retry", headers=headers)
    assert completed.status_code == 409

    _set(db_session_factory, created["id"], status="failed")
    other = client.post(
        "/auth/register", json={"email": "other@example.com", "password": "OtherPassword123!"}
    )
    assert other.status_code == 201
    token = client.post(
        "/auth/login", json={"email": "other@example.com", "password": "OtherPassword123!"}
    ).json()["access_token"]
    stranger = client.post(
        f"/documents/{created['id']}/retry", headers={"Authorization": f"Bearer {token}"}
    )
    assert stranger.status_code == 404

    os.remove(_document(db_session_factory, created["id"]).file_path)
    missing_file = client.post(f"/documents/{created['id']}/retry", headers=headers)
    assert missing_file.status_code == 409
    assert "no longer available" in missing_file.json()["detail"]


def test_the_background_worker_processes_uploads(
    db_session_factory, auth_headers, extractor, monkeypatch
):
    _user_id, headers = auth_headers
    monkeypatch.setattr(settings, "ingestion_worker_enabled", True)
    monkeypatch.setattr(main_module, "SessionLocal", db_session_factory)

    with TestClient(app) as client:
        created = _upload(client, headers)
        deadline = time.monotonic() + 10
        status = None
        while time.monotonic() < deadline:
            status = client.get(f"/documents/{created['id']}", headers=headers).json()["status"]
            if status == "completed":
                break
            time.sleep(0.05)
    assert status == "completed"
    assert app.state.ingestion_worker._thread.is_alive() is False


def test_orphaned_upload_files_are_removed(db_session_factory, auth_headers, extractor):
    _user_id, headers = auth_headers
    created = _upload(TestClient(app), headers)
    folder = Path(settings.upload_dir)
    old_orphan = folder / f"{uuid.uuid4()}.pdf"
    new_orphan = folder / f"{uuid.uuid4()}.pdf"
    old_orphan.write_bytes(PDF)
    new_orphan.write_bytes(PDF)
    hour_ago = time.time() - 2 * 60 * 60
    for path in (old_orphan, folder / f"{created['id']}.pdf"):
        os.utime(path, (hour_ago, hour_ago))

    assert ingestion.remove_orphan_files(db_session_factory, str(folder)) == 1
    assert not old_orphan.exists()
    assert new_orphan.exists()
    assert (folder / f"{created['id']}.pdf").exists()
