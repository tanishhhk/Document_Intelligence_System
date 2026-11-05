import threading
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.config import settings
from app.main import app
from app.models.document import Document
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.services import auth as auth_service
from app.services.auth import decode_access_token

PASSWORD = "Concurrent-Password-123"


def test_failed_logins_do_the_same_hashing_work_for_unknown_emails(db_session_factory, monkeypatch):
    client = TestClient(app)
    client.post("/auth/register", json={"email": "known@example.com", "password": PASSWORD})
    checks = []
    real_check = auth_service.verify_password

    def counting_check(plain, hashed):
        checks.append(hashed)
        return real_check(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", counting_check)
    monkeypatch.setattr(auth_api, "verify_password", counting_check)

    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    known = client.post("/auth/login", json={"email": "known@example.com", "password": "Wrong-password-123"})

    assert unknown.status_code == known.status_code == 401
    assert unknown.json() == known.json()
    assert len(checks) == 2
    assert all(hashed.startswith("$2b$") for hashed in checks)


def test_concurrent_registrations_for_one_email_create_one_account(db_session_factory):
    gate = threading.Barrier(5)
    statuses = []

    def register():
        gate.wait(10)
        response = TestClient(app).post(
            "/auth/register", json={"email": "Race@Example.com", "password": PASSWORD}
        )
        statuses.append(response.status_code)

    threads = [threading.Thread(target=register) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    assert sorted(statuses) == [201, 409, 409, 409, 409]
    with db_session_factory() as db:
        assert db.query(User).filter(User.email == "race@example.com").count() == 1


def test_logout_removes_expired_revocations_and_keeps_live_ones(db_session_factory, auth_headers):
    _user_id, headers = auth_headers
    now = int(time.time())
    with db_session_factory() as db:
        db.add_all(
            [
                RevokedToken(jti="expired-revocation", expires_at=now - 60),
                RevokedToken(jti="live-revocation", expires_at=now + 600),
            ]
        )
        db.commit()

    assert TestClient(app).post("/auth/logout", headers=headers).status_code == 204

    token_id = decode_access_token(headers["Authorization"].split()[1])["jti"]
    with db_session_factory() as db:
        remaining = {row.jti for row in db.query(RevokedToken).all()}
    assert remaining == {"live-revocation", token_id}


def test_uploaded_filenames_never_choose_the_storage_path(db_session_factory, auth_headers):
    _user_id, headers = auth_headers
    response = TestClient(app).post(
        "/documents/upload",
        headers={**headers, "Idempotency-Key": f"traversal-{uuid.uuid4().hex}"},
        files={"file": ("..\\..\\..//etc/passwd.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "passwd.pdf"

    with db_session_factory() as db:
        stored = Path(db.get(Document, body["id"]).file_path)
    assert stored.name == f"{body['id']}.pdf"
    assert stored.parent.resolve() == Path(settings.upload_dir).resolve()
