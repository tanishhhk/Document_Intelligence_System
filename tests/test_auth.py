import uuid
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import router
from app.database import Base, get_db
from app.models.user import User
from app.services.auth import decode_access_token

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

app = FastAPI()
app.include_router(router, prefix="/auth")


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def setup_function():
    Base.metadata.create_all(bind=test_engine)


def teardown_function():
    Base.metadata.drop_all(bind=test_engine)


def test_register_and_login_returns_signed_token():
    with TestClient(app) as client:
        registration = client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "StrongPassword123!"},
        )
        assert registration.status_code == 201, registration.text
        assert "hashed_password" not in registration.json()

        login = client.post(
            "/auth/login",
            json={"email": "NEW@example.com", "password": "StrongPassword123!"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["token_type"] == "bearer"

        payload = decode_access_token(login.json()["access_token"])
        assert payload["sub"] == "new@example.com"
        assert isinstance(payload["user_id"], str)


def test_login_rejects_invalid_credentials():
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "WrongPassword123!"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"


def test_duplicate_registration_is_rejected_case_insensitively():
    with TestClient(app) as client:
        first = client.post(
            "/auth/register",
            json={"email": "person@example.com", "password": "StrongPassword123!"},
        )
        second = client.post(
            "/auth/register",
            json={"email": "PERSON@example.com", "password": "OtherStrongPassword123!"},
        )
        assert first.status_code == 201
        assert second.status_code == 409


def test_registration_rejects_short_passwords():
    with TestClient(app) as client:
        response = client.post(
            "/auth/register",
            json={"email": "weak@example.com", "password": "short"},
        )
        assert response.status_code == 422


def test_registration_rejects_passwords_over_bcrypt_byte_limit():
    with TestClient(app) as client:
        response = client.post(
            "/auth/register",
            json={"email": "long@example.com", "password": "é" * 40},
        )
        assert response.status_code == 422
