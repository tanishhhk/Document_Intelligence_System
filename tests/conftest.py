import os

# Use test-only settings before application modules instantiate Pydantic Settings.
os.environ["DATABASE_URL"] = "sqlite:///./document_intelligence.db"
os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-long-enough-for-hs512-signatures-0001"
# No answer provider is configured, so no test can reach a real model API.
os.environ["GEMINI_API_KEY"] = ""
os.environ["UPLOAD_DIR"] = "./uploads"
os.environ["MAX_FILE_SIZE"] = "10485760"
os.environ["AUTO_MIGRATE"] = "false"
os.environ["INGESTION_WORKER_ENABLED"] = "false"
# The app-wide rate limiter keeps state across tests and every test client
# shares one address. tests/test_rate_limit.py checks limits on its own instances.
os.environ["AUTH_REQUESTS_PER_MINUTE"] = "100000"
os.environ["UPLOAD_REQUESTS_PER_MINUTE"] = "100000"
os.environ["CHAT_REQUESTS_PER_MINUTE"] = "100000"
os.environ["DEFAULT_REQUESTS_PER_MINUTE"] = "100000"

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.main import app
from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.database import TEST_DATABASE_URL


@pytest.fixture()
def db_session_factory(tmp_path, monkeypatch):
    """A real file or server database, so concurrent requests use separate connections."""
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
    else:
        engine = create_engine(
            f"sqlite:///{(tmp_path / 'idempotency.db').as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    yield factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def auth_headers(db_session_factory):
    db = db_session_factory()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email="uploader@example.com",
            hashed_password=get_password_hash("UploaderPassword123!"),
        )
        db.add(user)
        db.commit()
        token = create_access_token(
            {"sub": user.email, "user_id": user.id}, expires_delta=timedelta(minutes=5)
        )
        return user.id, {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


