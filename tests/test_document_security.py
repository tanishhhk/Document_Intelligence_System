import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import chat as chat_api
from app.api import documents as documents_api
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
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


def make_token(user):
    return create_access_token(
        {"sub": user.email, "user_id": user.id},
        expires_delta=timedelta(minutes=5),
    )


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


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
        return owner, stranger, make_token(owner), make_token(stranger)
    finally:
        db.close()


def add_document(owner, *, text=None):
    document_id = str(uuid.uuid4())
    db = TestingSessionLocal()
    try:
        db.add(
            Document(
                id=document_id,
                user_id=owner.id,
                filename="policy.pdf",
                file_path="/tmp/policy.pdf",
                file_size=120,
                status="completed",
            )
        )
        if text is not None:
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                chunk_index=0,
                chunk_text=text,
            )
            chunk.set_embedding([1.0, 0.0])
            db.add(chunk)
        db.commit()
        return document_id
    finally:
        db.close()


def test_anonymous_requests_cannot_list_documents_or_ask_questions(client):
    assert client.get("/documents/list").status_code == 401
    assert client.post(
        "/chat/ask",
        json={"question": "Question", "document_id": "missing"},
    ).status_code == 401


def test_document_routes_are_registered_without_duplicate_prefixes(client, users_and_tokens):
    _owner, _stranger, owner_token, _stranger_token = users_and_tokens
    assert client.get("/documents/list", headers=bearer(owner_token)).status_code == 200
    assert client.get("/documents/documents/list", headers=bearer(owner_token)).status_code == 404


def test_users_cannot_read_delete_or_query_another_users_document(client, users_and_tokens):
    owner, _stranger, owner_token, stranger_token = users_and_tokens
    document_id = add_document(owner, text="The cancellation window is 30 days.")

    assert client.get(
        f"/documents/{document_id}", headers=bearer(stranger_token)
    ).status_code == 404
    assert client.delete(
        f"/documents/{document_id}", headers=bearer(stranger_token)
    ).status_code == 404
    assert client.post(
        "/chat/ask",
        headers=bearer(stranger_token),
        json={"question": "What is the cancellation window?", "document_id": document_id},
    ).status_code == 404

    assert client.get(
        f"/documents/{document_id}", headers=bearer(owner_token)
    ).status_code == 200


def test_document_list_contains_only_the_current_users_documents(client, users_and_tokens):
    owner, _stranger, owner_token, stranger_token = users_and_tokens
    owner_id = add_document(owner)
    db = TestingSessionLocal()
    try:
        stranger = db.query(User).filter(User.email == "stranger@example.com").one()
        stranger_id = add_document(stranger)
    finally:
        db.close()

    owner_ids = {item["id"] for item in client.get(
        "/documents/list", headers=bearer(owner_token)
    ).json()}
    stranger_ids = {item["id"] for item in client.get(
        "/documents/list", headers=bearer(stranger_token)
    ).json()}
    assert owner_ids == {owner_id}
    assert stranger_ids == {stranger_id}


def test_document_identifier_is_treated_as_data_not_sql(client, users_and_tokens):
    _owner, _stranger, _owner_token, stranger_token = users_and_tokens
    response = client.get(
        "/documents/%27%20OR%201%3D1%20--",
        headers=bearer(stranger_token),
    )
    assert response.status_code == 404


def test_upload_sets_server_side_owner_and_indexes_chunks(
    client, users_and_tokens, monkeypatch, tmp_path
):
    owner, _stranger, owner_token, _stranger_token = users_and_tokens
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(
        documents_api,
        "_extract_and_embed_pdf",
        lambda _path: (["Example passage"], [[0.1, 0.2]]),
    )

    response = client.post(
        "/documents/upload",
        headers=bearer(owner_token),
        files={"file": ("sample.pdf", b"%PDF-1.7\nminimal test PDF", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    result = response.json()

    db = TestingSessionLocal()
    try:
        stored = db.query(Document).filter(Document.id == result["id"]).one()
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == result["id"]
        ).all()
        assert stored.user_id == owner.id
        assert stored.status == "completed"
        assert len(chunks) == 1
    finally:
        db.close()


def test_upload_rejects_non_pdf_content_and_removes_temporary_file(
    client, users_and_tokens, monkeypatch, tmp_path
):
    _owner, _stranger, owner_token, _stranger_token = users_and_tokens
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    response = client.post(
        "/documents/upload",
        headers=bearer(owner_token),
        files={"file": ("fake.pdf", b"not a PDF", "application/pdf")},
    )
    assert response.status_code == 415
    assert list(tmp_path.iterdir()) == []


def test_upload_enforces_size_limit_and_removes_partial_file(
    client, users_and_tokens, monkeypatch, tmp_path
):
    _owner, _stranger, owner_token, _stranger_token = users_and_tokens
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "max_file_size", 8)
    response = client.post(
        "/documents/upload",
        headers=bearer(owner_token),
        files={"file": ("large.pdf", b"%PDF-1.7\ncontent beyond limit", "application/pdf")},
    )
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_scan_without_selectable_text_is_rejected(client, users_and_tokens, monkeypatch, tmp_path):
    _owner, _stranger, owner_token, _stranger_token = users_and_tokens
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    def no_text(_path):
        raise ValueError("No selectable text was found. Scanned or image-only PDFs need OCR.")

    monkeypatch.setattr(documents_api, "_extract_and_embed_pdf", no_text)
    response = client.post(
        "/documents/upload",
        headers=bearer(owner_token),
        files={"file": ("scan.pdf", b"%PDF-1.7\nscan", "application/pdf")},
    )
    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_chat_uses_owned_document_and_returns_source_metadata(
    client, users_and_tokens, monkeypatch
):
    owner, _stranger, owner_token, _stranger_token = users_and_tokens
    document_id = add_document(owner, text="The cancellation window is 30 days.")
    monkeypatch.setattr(
        chat_api, "generate_single_embedding", lambda _question: [1.0, 0.0]
    )
    monkeypatch.setattr(
        chat_api, "generate_answer", lambda _question, _context: "30 days"
    )

    response = client.post(
        "/chat/ask",
        headers=bearer(owner_token),
        json={
            "question": "What is the cancellation window?",
            "document_id": document_id,
            "top_k": 1,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"] == "30 days"
    assert body["document_name"] == "policy.pdf"
    assert body["sources"][0]["chunk_index"] == 0
    assert body["metadata"]["top_k_used"] == 1


def test_top_k_and_question_length_are_bounded(client, users_and_tokens):
    _owner, _stranger, _owner_token, stranger_token = users_and_tokens
    too_many = client.post(
        "/chat/ask",
        headers=bearer(stranger_token),
        json={"question": "Question", "document_id": "unknown", "top_k": 1000},
    )
    too_long = client.post(
        "/chat/ask",
        headers=bearer(stranger_token),
        json={"question": "q" * 4001, "document_id": "unknown"},
    )
    assert too_many.status_code == 422
    assert too_long.status_code == 422
