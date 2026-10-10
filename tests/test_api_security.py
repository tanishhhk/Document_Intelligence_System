"""Regression tests for route registration, bearer auth, and document ownership."""

import os
import uuid
from datetime import timedelta

# Keep test imports independent of a developer's local .env. main.py's default
# SQLite file is ignored by Git; all assertions use the isolated in-memory DB.
os.environ["DATABASE_URL"] = "sqlite:///./document_intelligence.db"
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")
os.environ.setdefault("GEMINI_API_KEY", "test-only-placeholder-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import documents as documents_api
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.document import Document
from app.models.user import User
from app.services.auth import create_access_token, get_password_hash

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def users_and_tokens(client):
    db = TestingSessionLocal()
    try:
        owner = User(
            id=str(uuid.uuid4()),
            email="owner@example.com",
            hashed_password=get_password_hash("OwnerPassword123!"),
        )
        stranger = User(
            id=str(uuid.uuid4()),
            email="stranger@example.com",
            hashed_password=get_password_hash("StrangerPassword123!"),
        )
        db.add_all([owner, stranger])
        db.commit()
        owner_token = create_access_token(
            {"sub": owner.email, "user_id": owner.id},
            expires_delta=timedelta(minutes=5),
        )
        stranger_token = create_access_token(
            {"sub": stranger.email, "user_id": stranger.id},
            expires_delta=timedelta(minutes=5),
        )
        return owner, stranger, owner_token, stranger_token
    finally:
        db.close()


def test_auth_routes_have_single_prefix_and_issue_usable_tokens(client):
    registration = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "StrongPassword123!"},
    )
    assert registration.status_code == 201
    assert "hashed_password" not in registration.json()

    login = client.post(
        "/auth/login",
        json={"email": "NEW@example.com", "password": "StrongPassword123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    documents = client.get(
        "/documents/list",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert documents.status_code == 200
    assert documents.json() == []


def test_protected_endpoints_reject_anonymous_requests(client):
    assert client.get("/documents/list").status_code == 401
    assert client.post(
        "/chat/ask",
        json={"question": "What does it say?", "document_id": "unknown"},
    ).status_code == 401


def test_user_cannot_read_delete_or_ask_about_another_users_document(
    client, users_and_tokens
):
    owner, stranger, owner_token, stranger_token = users_and_tokens
    db = TestingSessionLocal()
    document_id = str(uuid.uuid4())
    try:
        db.add(
            Document(
                id=document_id,
                user_id=owner.id,
                filename="private.pdf",
                file_path="/tmp/private.pdf",
                file_size=100,
                status="completed",
            )
        )
        db.commit()
    finally:
        db.close()

    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}
    assert client.get(
        "/documents/list", headers=stranger_headers
    ).status_code == 200
    assert client.get(
        "/documents/list", headers=stranger_headers
    ).json() == []
    assert client.get(
        f"/documents/{document_id}", headers=stranger_headers
    ).status_code == 404
    assert client.delete(
        f"/documents/{document_id}", headers=stranger_headers
    ).status_code == 404
    assert client.post(
        "/chat/ask",
        headers=stranger_headers,
        json={"question": "Tell me about this file", "document_id": document_id},
    ).status_code == 404

    # The owner can still retrieve their own document.
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    assert client.get(
        f"/documents/{document_id}", headers=owner_headers
    ).status_code == 200


def test_pdf_upload_is_owned_by_authenticated_user_and_streamed(
    client, users_and_tokens, monkeypatch, tmp_path
):
    _owner, _stranger, owner_token, _stranger_token = users_and_tokens
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(
        documents_api,
        "_extract_and_embed_pdf",
        lambda _path: (["sample passage"], [[0.1, 0.2]]),
    )

    response = client.post(
        "/documents/upload",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("sample.pdf", b"%PDF-1.7\nminimal test fixture", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "sample.pdf"
    assert body["file_size"] > 0

    db = TestingSessionLocal()
    try:
        stored = db.query(Document).filter(Document.id == body["id"]).one()
        assert stored.user_id == _owner.id
        assert stored.status == "completed"
    finally:
        db.close()


def test_top_k_is_bounded_before_retrieval(client, users_and_tokens):
    _owner, _stranger, _owner_token, stranger_token = users_and_tokens
    response = client.post(
        "/chat/ask",
        headers={"Authorization": f"Bearer {stranger_token}"},
        json={"question": "Question", "document_id": "any-id", "top_k": 1000},
    )
    assert response.status_code == 422
