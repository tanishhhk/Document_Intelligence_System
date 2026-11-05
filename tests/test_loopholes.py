"""Attempts to get around authentication, ownership, validation and limits through the API."""
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.config import settings
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services import llm
from app.services.auth import create_access_token, get_password_hash
from tests.fakes import vector

PDF = b"%PDF-1.7\nsample"
PUBLIC_ROUTES = {("GET", "/"), ("GET", "/health"), ("GET", "/ready"), ("POST", "/auth/register"), ("POST", "/auth/login")}


def _routes():
    # The OpenAPI schema lists every route, including those of included routers.
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            yield method.upper(), path


def _concrete(path):
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


@pytest.fixture()
def two_users(db_session_factory):
    """An owner with a completed, indexed document, and a stranger."""
    tokens = {}
    with db_session_factory() as db:
        for name in ("owner", "stranger"):
            user = User(id=str(uuid.uuid4()), email=f"{name}@example.com", hashed_password=get_password_hash("Password-123456"))
            db.add(user)
            db.flush()
            tokens[name] = (user.id, {"Authorization": f"Bearer {create_access_token({'sub': user.email, 'user_id': user.id})}"})
        document_id = str(uuid.uuid4())
        db.add(Document(id=document_id, user_id=tokens["owner"][0], filename="owner.pdf",
                        file_path=f"{settings.upload_dir}/{document_id}.pdf", file_size=5, status="failed"))
        db.flush()
        chunk = DocumentChunk(id=str(uuid.uuid4()), document_id=document_id, chunk_index=0, chunk_text="Owner secret.",
                              page_start=1, page_end=1, embedding_model="all-MiniLM-L6-v2", embedding_dim=384)
        chunk.set_embedding(vector(0))
        db.add(chunk)
        db.commit()
    return tokens, document_id


# Authentication coverage


def test_every_route_outside_the_public_list_requires_authentication(db_session_factory):
    """New routes are protected by default: this fails if one is added without auth."""
    client = TestClient(app)
    checked = 0
    for method, path in _routes():
        if (method, path) in PUBLIC_ROUTES:
            continue
        for headers in ({}, {"Authorization": "Bearer not-a-token"}, {"Authorization": "Basic dXNlcjpwYXNz"}):
            response = client.request(method, _concrete(path), headers=headers, json={})
            assert response.status_code == 401, f"{method} {path} with {headers} returned {response.status_code}"
        checked += 1
    assert checked >= 8  # Guards against the route listing silently finding nothing.


def test_tokens_for_deleted_users_stop_working(db_session_factory, auth_headers):
    user_id, headers = auth_headers
    with db_session_factory() as db:
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    assert TestClient(app).get("/documents", headers=headers).status_code == 401


def test_a_token_cannot_be_reused_for_another_user_by_editing_the_subject(db_session_factory, two_users):
    tokens, _document_id = two_users
    stranger_id = tokens["stranger"][0]
    forged = create_access_token({"sub": "owner@example.com", "user_id": stranger_id})
    assert TestClient(app).get("/documents", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


# Ownership


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("GET", "/documents/{id}", None),
        ("DELETE", "/documents/{id}", None),
        ("POST", "/documents/{id}/retry", None),
        ("POST", "/chat/ask", {"question": "What is the secret?", "document_id": "{id}"}),
    ],
)
def test_another_users_document_cannot_be_touched(two_users, db_session_factory, method, path, body):
    tokens, document_id = two_users
    payload = {k: v.replace("{id}", document_id) for k, v in body.items()} if body else None
    response = TestClient(app).request(method, path.replace("{id}", document_id),
                                       headers=tokens["stranger"][1], json=payload)
    assert response.status_code == 404
    assert "Owner secret" not in response.text
    with db_session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None and document.status == "failed"


def test_another_users_documents_never_appear_in_lists_or_search(two_users):
    tokens, _document_id = two_users
    client = TestClient(app)
    for params in ({}, {"q": "owner"}, {"status": "failed"}):
        assert client.get("/documents", headers=tokens["stranger"][1], params=params).json()["total"] == 0
    assert client.get("/documents/list", headers=tokens["stranger"][1]).json() == []


def test_idempotency_keys_are_scoped_to_their_user(two_users):
    tokens, _document_id = two_users
    client = TestClient(app)
    key = {"Idempotency-Key": "shared-key-between-users"}
    files = {"file": ("a.pdf", PDF, "application/pdf")}
    first = client.post("/documents/upload", headers={**tokens["owner"][1], **key}, files=files)
    second = client.post("/documents/upload", headers={**tokens["stranger"][1], **key}, files=files)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_registration_ignores_fields_the_client_should_not_set(db_session_factory):
    response = TestClient(app).post(
        "/auth/register",
        json={"email": "new@example.com", "password": "Password-123456", "id": "chosen-id",
              "hashed_password": "x", "is_admin": True},
    )
    assert response.status_code == 201
    assert response.json()["id"] != "chosen-id"
    with db_session_factory() as db:
        assert db.query(User).filter(User.email == "new@example.com").one().hashed_password.startswith("$2b$")


# Malformed and hostile identifiers


@pytest.mark.parametrize(
    "document_id",
    ["../../etc/passwd", "..%2F..%2Fetc", "' OR '1'='1", "1; DROP TABLE documents; --", "%00", "x" * 5000,
     "‮لا", "\U0001f4c4", "null", "-1", "0"],
)
def test_hostile_document_ids_are_simply_not_found(two_users, document_id):
    tokens, _document_id = two_users
    client = TestClient(app)
    for method, path in (("GET", f"/documents/{document_id}"), ("DELETE", f"/documents/{document_id}")):
        response = client.request(method, path, headers=tokens["owner"][1])
        assert response.status_code in (404, 405, 307), (path, response.status_code)
    ask = client.post("/chat/ask", headers=tokens["owner"][1], json={"question": "q", "document_id": document_id[:128]})
    assert ask.status_code in (404, 422)


# Upload validation boundaries


@pytest.mark.parametrize(
    "filename, status_code",
    [
        ("report.pdf", 201), ("REPORT.PDF", 201), ("archive.tar.pdf", 201), ("résumé \U0001f4c4.pdf", 201),
        ("report.pdf.exe", 415), ("report", 415), ("", 422), (".pdf", 201), ("report.pdf ", 415),
    ],
)
def test_upload_filenames(two_users, filename, status_code):
    tokens, _document_id = two_users
    response = TestClient(app).post(
        "/documents/upload",
        headers={**tokens["owner"][1], "Idempotency-Key": f"name-{uuid.uuid4().hex}"},
        files={"file": (filename, PDF, "application/pdf")},
    )
    assert response.status_code == status_code, response.text


def test_stored_filenames_are_bounded_and_free_of_control_characters(two_users):
    tokens, _document_id = two_users
    response = TestClient(app).post(
        "/documents/upload",
        headers={**tokens["owner"][1], "Idempotency-Key": f"name-{uuid.uuid4().hex}"},
        files={"file": ("a\x07b\x1b[31m" + "x" * 1000 + ".pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201
    stored = response.json()["filename"]
    assert len(stored) <= 255
    assert stored.endswith(".pdf")
    assert not any(ord(c) < 32 or ord(c) == 127 for c in stored)


@pytest.mark.parametrize(
    "content, status_code",
    [
        (b"x" * 1000 + b"%PDF-1.7", 201),  # A header within the first 1,024 bytes is valid.
        (b"x" * 1020 + b"%PDF-1.7", 415),  # Starts inside the window but does not fit in it.
        (b"x" * 2000 + b"%PDF-1.7", 415),
        (b"%pdf-1.7", 415),
        (b"PK\x03\x04%PDF-", 201),  # Signature checks alone cannot reject polyglots; parsing fails later.
        (b"", 400),
    ],
)
def test_pdf_signature_boundaries(two_users, content, status_code):
    tokens, _document_id = two_users
    response = TestClient(app).post(
        "/documents/upload",
        headers={**tokens["owner"][1], "Idempotency-Key": f"sig-{uuid.uuid4().hex}"},
        files={"file": ("a.pdf", content, "text/plain")},
    )
    assert response.status_code == status_code


@pytest.mark.parametrize(
    "key, status_code",
    [("a" * 15, 422), ("a" * 16, 201), ("a" * 128, 201), ("a" * 129, 422), ("has space-in-it-x", 400),
     ("slash/inside/key-x", 400), ("café-key-0000000000".encode(), 400), ("dots.and_under-scores", 201)],
)
def test_idempotency_key_boundaries(two_users, key, status_code):
    tokens, _document_id = two_users
    response = TestClient(app).post(
        "/documents/upload",
        headers={**tokens["owner"][1], "Idempotency-Key": key},
        files={"file": ("a.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == status_code


@pytest.mark.parametrize(
    "parts, status_code, stored",
    [
        ([("first.pdf", PDF), ("second.exe", b"MZ")], 415, None),
        ([("first.exe", b"MZ"), ("second.pdf", PDF)], 201, "second.pdf"),
    ],
)
def test_with_two_file_fields_the_file_that_is_stored_is_the_one_validated(two_users, parts, status_code, stored):
    tokens, _document_id = two_users
    response = TestClient(app).post(
        "/documents/upload",
        headers={**tokens["owner"][1], "Idempotency-Key": f"two-{uuid.uuid4().hex}"},
        files=[("file", (name, content, "application/octet-stream")) for name, content in parts],
    )
    assert response.status_code == status_code
    if stored:
        assert response.json()["filename"] == stored


# Credential boundaries


@pytest.mark.parametrize(
    "password, status_code",
    [("a" * 11, 422), ("a" * 12, 201), ("a" * 72, 201), ("a" * 73, 422),
     ("€" * 24, 201), ("€" * 25, 422), (" " * 12, 201), ("a" * 10_000, 422)],
    ids=["11", "12", "72", "73", "72-utf8-bytes", "75-utf8-bytes", "spaces", "huge"],
)
def test_password_boundaries(db_session_factory, password, status_code):
    client = TestClient(app)
    email = f"p{uuid.uuid4().hex[:8]}@example.com"
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == status_code
    if status_code == 201:
        assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 200


@pytest.mark.parametrize(
    "email",
    ["not-an-email", "a@b", "@example.com", "user@", "user@@example.com", "user@exa mple.com", "x" * 300 + "@example.com"],
)
def test_malformed_emails_are_rejected(db_session_factory, email):
    response = TestClient(app).post("/auth/register", json={"email": email, "password": "Password-123456"})
    assert response.status_code == 422


def test_email_case_and_internationalised_domains_round_trip(db_session_factory):
    client = TestClient(app)
    assert client.post("/auth/register", json={"email": "User@Bücher.example", "password": "Password-123456"}).status_code == 201
    assert client.post("/auth/login", json={"email": "user@bücher.example", "password": "Password-123456"}).status_code == 200
    assert client.post("/auth/register", json={"email": "USER@BÜCHER.example", "password": "Password-123456"}).status_code == 409


# Question payloads


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "", "document_id": "x"},
        {"question": "   \n\t ", "document_id": "x"},
        {"question": "q" * 4001, "document_id": "x"},
        {"question": "q", "document_id": ""},
        {"question": "q", "document_id": "x" * 129},
        {"question": "q", "document_id": "x", "top_k": 0},
        {"question": "q", "document_id": "x", "top_k": -1},
        {"question": "q", "document_id": "x", "top_k": 11},
        {"question": "q", "document_id": "x", "top_k": 2.5},
        {"question": "q", "document_id": "x", "top_k": None},
        {"question": ["q"], "document_id": "x"},
        {"question": {"$ne": ""}, "document_id": "x"},
        {"document_id": "x"},
        {},
    ],
)
def test_invalid_questions_are_rejected(two_users, payload):
    tokens, _document_id = two_users
    response = TestClient(app).post("/chat/ask", headers=tokens["owner"][1], json=payload)
    assert response.status_code == 422


def test_deeply_nested_json_is_rejected_cleanly(two_users):
    tokens, _document_id = two_users
    body = "[" * 50_000 + "]" * 50_000
    response = TestClient(app, raise_server_exceptions=False).post(
        "/chat/ask", headers={**tokens["owner"][1], "Content-Type": "application/json"}, content=body
    )
    assert response.status_code in (400, 422)


def test_a_question_at_the_length_limit_is_accepted(two_users, monkeypatch, db_session_factory):
    tokens, document_id = two_users
    with db_session_factory() as db:
        db.query(Document).filter(Document.id == document_id).update({Document.status: "completed"})
        db.commit()
    monkeypatch.setattr(chat_api, "generate_single_embedding", lambda _q: vector(0))
    monkeypatch.setattr(chat_api, "generate_answer", lambda q, s, f=None: llm.Answer("Yes [S1].", "fake", "m"))
    response = TestClient(app).post(
        "/chat/ask", headers=tokens["owner"][1], json={"question": "q" * 4000, "document_id": document_id}
    )
    assert response.status_code == 200


# Rate limit evasion


@pytest.mark.parametrize("variant", ["/AUTH/LOGIN", "//auth/login", "/auth/login/", "/auth/login%2F", "/auth//login"])
def test_login_path_variants_do_not_get_extra_attempts(db_session_factory, monkeypatch, variant):
    monkeypatch.setattr(settings, "auth_requests_per_minute", 3)
    client = TestClient(app, client=(f"198.18.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}", 1))
    credentials = {"email": "nobody@example.com", "password": "Wrong-password-1"}
    logins = 0
    for _ in range(10):
        response = client.post(variant, json=credentials)
        logins += response.status_code == 401  # The login handler actually ran.
    assert logins <= 3


def test_methods_a_route_does_not_support_are_rejected():
    client = TestClient(app)
    assert client.put("/auth/login", json={}).status_code == 405
    assert client.request("PATCH", "/documents/x").status_code in (401, 405)


def test_nul_bytes_are_handled_without_a_database_error(two_users):
    """PostgreSQL rejects NUL bytes in text; they must not reach a query."""
    tokens, _document_id = two_users
    client = TestClient(app, raise_server_exceptions=False)
    headers = tokens["owner"][1]
    assert client.get("/documents/%00", headers=headers).status_code == 404
    assert client.post("/documents/%00/retry", headers=headers).status_code == 404
    assert client.post("/chat/ask", headers=headers, json={"question": "q", "document_id": "a\x00b"}).status_code == 404
    assert client.get("/documents", headers=headers, params={"q": "a\x00b"}).status_code == 422
