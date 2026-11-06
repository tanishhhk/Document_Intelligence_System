"""Daily limits, the library cap, onboarding profiles, lenses, speech cleanup and headers."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.config import settings
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services import lenses, llm, story as story_service, usage
from app.services.auth import create_access_token, get_password_hash
from app.services.speech import display_name, speakable
from tests.fakes import vector


def _user(factory):
    with factory() as db:
        user = User(id=str(uuid.uuid4()), email=f"u{uuid.uuid4().hex[:8]}@example.com",
                    hashed_password=get_password_hash("Password-123456"))
        db.add(user)
        db.commit()
        token = create_access_token({"sub": user.email, "user_id": user.id})
        return user.id, {"Authorization": f"Bearer {token}"}


def _document(factory, user_id):
    with factory() as db:
        document_id = str(uuid.uuid4())
        db.add(Document(id=document_id, user_id=user_id, filename="report.pdf",
                        file_path=f"{settings.upload_dir}/{document_id}.pdf", file_size=5, status="completed"))
        db.flush()
        chunk = DocumentChunk(id=str(uuid.uuid4()), document_id=document_id, chunk_index=0,
                              chunk_text="The fee is 30 days.", page_start=1, page_end=1,
                              embedding_model="all-MiniLM-L6-v2", embedding_dim=384)
        chunk.set_embedding(vector(0))
        db.add(chunk)
        db.commit()
        return document_id


@pytest.fixture()
def client(db_session_factory):
    return TestClient(app)


def _ask(client, headers, document_id):
    return client.post("/chat/ask", headers=headers, json={"question": "What is the fee?", "document_id": document_id})


# Daily limits


def test_questions_stop_at_the_daily_limit_with_a_reset_time(db_session_factory, client, monkeypatch):
    monkeypatch.setattr(settings, "daily_questions_per_user", 2)
    monkeypatch.setattr(chat_api, "generate_single_embedding", lambda _q: vector(0))
    user_id, headers = _user(db_session_factory)
    document_id = _document(db_session_factory, user_id)
    assert [_ask(client, headers, document_id).status_code for _ in range(2)] == [200, 200]
    refused = _ask(client, headers, document_id)
    assert refused.status_code == 429
    assert "2 questions" in refused.json()["detail"]
    assert 0 < int(refused.headers["Retry-After"]) <= 86400

    other_id, other = _user(db_session_factory)
    assert _ask(client, other, _document(db_session_factory, other_id)).status_code == 200  # Per user.

    report = client.get("/auth/me/usage", headers=headers).json()
    assert report["used"]["question"] == 2 and report["limits"]["question"] == 2
    assert report["documents"] == 1


def test_uploads_respect_the_daily_limit_and_the_library_cap(db_session_factory, client, monkeypatch):
    monkeypatch.setattr(settings, "daily_uploads_per_user", 1)

    def upload(headers):
        return client.post("/documents/upload", headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
                           files={"file": ("a.pdf", b"%PDF-1.7\n" + uuid.uuid4().bytes, "application/pdf")})

    _user_id, headers = _user(db_session_factory)
    assert upload(headers).status_code == 201
    assert upload(headers).status_code == 429

    monkeypatch.setattr(settings, "daily_uploads_per_user", 100)
    monkeypatch.setattr(settings, "max_documents_per_user", 1)
    full = upload(headers)
    assert full.status_code == 409 and "Delete one" in full.json()["detail"]


def test_stories_count_against_their_own_limit(db_session_factory, client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "daily_stories_per_user", 1)
    monkeypatch.setattr(settings, "video_dir", str(tmp_path))
    user_id, headers = _user(db_session_factory)
    first, second = _document(db_session_factory, user_id), _document(db_session_factory, user_id)
    assert client.post(f"/videos/generate/{first}", headers=headers).status_code == 202
    # Asking again for the running story returns it without counting twice.
    assert client.post(f"/videos/generate/{first}", headers=headers).status_code == 202
    from app.services import video_jobs
    video_jobs.process_pending(db_session_factory)
    assert client.post(f"/videos/generate/{second}", headers=headers).status_code == 429


def test_concurrent_increments_cannot_pass_the_limit(db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "daily_questions_per_user", 3)
    user_id, _headers = _user(db_session_factory)
    allowed = 0
    for _ in range(6):
        with db_session_factory() as db:
            try:
                usage.consume(db, user_id, "question")
                db.commit()
                allowed += 1
            except Exception:
                db.rollback()
    assert allowed == 3


# Profiles and lenses


@pytest.mark.parametrize(
    "profile, status",
    [({"profession": "student", "focus": "exam"}, 200), ({"profession": "employee", "focus": "legal"}, 200),
     ({"profession": "student", "focus": "legal"}, 422), ({"profession": "pirate", "focus": "exam"}, 422),
     ({"profession": "student", "focus": "exam", "is_admin": True}, 422)],
)
def test_profiles_accept_only_known_pairs(db_session_factory, client, profile, status):
    _user_id, headers = _user(db_session_factory)
    response = client.put("/auth/me/profile", headers=headers, json=profile)
    assert response.status_code == status
    if status == 200:
        me = client.get("/auth/me", headers=headers).json()
        assert (me["profession"], me["focus"]) == (profile["profession"], profile["focus"])


def test_every_focus_has_answer_and_story_guidance():
    focuses = {focus for options in lenses.PROFESSIONS.values() for focus in options}
    assert focuses == set(lenses.ANSWER_FOCUS) == set(lenses.STORY_FOCUS)


def test_the_focus_adds_guidance_without_dropping_the_grounding_rules(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "generate_text", lambda system, user: seen.setdefault("system", system) and None)
    llm.generate_answer("q", [], "legal")
    assert seen["system"].startswith(llm.SYSTEM_INSTRUCTION)
    assert "obligations" in seen["system"]
    seen.clear()
    llm.generate_answer("q", [], "not-a-focus")
    assert seen["system"] == llm.SYSTEM_INSTRUCTION
    assert "Audience:" in story_service._system_instruction("strict", "overview", "exam")
    assert "Audience:" not in story_service._system_instruction("strict", "overview", None)


# Speech


@pytest.mark.parametrize(
    "text, spoken",
    [("The Tale of quarterly_report.", "The Tale of quarterly report."),
     ("Region | Q3 2026 | 198", "Region Q3 2026 198"),
     ("Up 9% & rising", "Up 9 percent and rising"),
     ("Pages 3-5 on 2026-11-05", "Pages 3 to 5 on 2026-11-05"),
     ("See https://example.com/a_b now", "See a link now"),
     ("**Bold** #tag `code`", "Bold tag code"),
     ("Before — after", "Before, after")],
)
def test_narration_reads_no_symbols_aloud(text, spoken):
    assert speakable(text) == spoken


def test_slide_labels_lose_underscores():
    assert display_name("quarterly_report__v2|final") == "quarterly report v2 final"


# Headers


def test_responses_carry_security_headers(client):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "content-security-policy" not in client.get("/docs").headers


def test_browsers_may_send_the_profile_update(client):
    preflight = client.options(
        "/auth/me/profile",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT",
                 "Access-Control-Request-Headers": "authorization,content-type"},
    )
    assert preflight.status_code == 200
    assert "PUT" in preflight.headers["access-control-allow-methods"]


def test_hosted_postgres_urls_use_the_installed_driver():
    from app.config import Settings

    for url in ("postgres://u:p@db.example:5432/dis", "postgresql://u:p@db.example:5432/dis"):
        configured = Settings(database_url=url, secret_key="x" * 40)
        assert configured.database_url == "postgresql+psycopg://u:p@db.example:5432/dis"
    assert Settings(database_url="sqlite:///./a.db", secret_key="x" * 40).database_url == "sqlite:///./a.db"
