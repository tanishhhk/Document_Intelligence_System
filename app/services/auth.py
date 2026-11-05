from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

import bcrypt
import jwt

from app.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    payload.setdefault("jti", str(uuid.uuid4()))
    lifetime = expires_delta if expires_delta is not None else timedelta(minutes=15)
    payload["exp"] = datetime.now(timezone.utc) + lifetime
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"require": ["exp", "jti", "sub"]},
        )
    except jwt.PyJWTError:
        return None


def token_user_id(token: str) -> Optional[str]:
    """Return the user ID from a validly signed token, without a database lookup.

    Only for keying rate limits. Authorization must use get_current_user,
    which also checks revocation and that the user still exists.
    """
    payload = decode_access_token(token)
    user_id = payload.get("user_id") if payload else None
    return user_id if isinstance(user_id, str) and user_id else None
