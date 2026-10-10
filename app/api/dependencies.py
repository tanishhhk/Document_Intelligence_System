from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token

# HTTP Bearer accurately describes this API: login accepts JSON credentials,
# rather than the OAuth2 password-grant form expected by OAuth2PasswordBearer.
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve a signed bearer token to an existing database user."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise _unauthorized()

    email = payload.get("sub")
    token_user_id = payload.get("user_id")
    if not isinstance(email, str) or not email or not isinstance(token_user_id, str):
        raise _unauthorized()

    user = db.query(User).filter(User.email == email).first()
    if user is None or user.id != token_user_id:
        raise _unauthorized()

    return user
