from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired authentication credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve a signed bearer token to an existing database user."""
    payload = decode_access_token(token)
    if not payload:
        raise _credentials_error

    email = payload.get("sub")
    token_user_id = payload.get("user_id")
    if not isinstance(email, str) or not email or not isinstance(token_user_id, str):
        raise _credentials_error

    user = db.query(User).filter(User.email == email).first()
    if user is None or user.id != token_user_id:
        raise _credentials_error

    return user
