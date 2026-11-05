from datetime import timedelta
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import bearer_scheme, get_current_user
from app.config import settings
from app.database import get_db
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.models.document import Document
from app.schemas.user import ProfileUpdate, Token, UsageResponse, UserCreate, UserLogin, UserResponse
from app.services import lenses, usage
from app.services.auth import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
    verify_password_for_missing_user,
)

router = APIRouter(tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    email = str(user_data.email).strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    user = User(email=email, hashed_password=get_password_hash(user_data.password))
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        ) from None
    return user


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    email = str(user_data.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if user is None:
        valid = verify_password_for_missing_user(user_data.password)
    else:
        valid = verify_password(user_data.password, user.hashed_password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """The signed-in user. Lets a client check that a stored token is still valid."""
    return current_user


@router.put("/me/profile", response_model=UserResponse)
def update_profile(
    profile: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save the profession and focus chosen in onboarding."""
    if not lenses.is_valid(profile.profession, profile.focus):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a profession and one of its focus options.",
        )
    current_user.profession, current_user.focus = profile.profession, profile.focus
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/usage", response_model=UsageResponse)
def my_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Today's uploads, questions and stories, against the daily limits."""
    return {
        "limits": usage.limits(),
        "used": usage.used_today(db, current_user.id),
        "resets_in_seconds": usage.seconds_until_reset(),
        "max_documents": settings.max_documents_per_user,
        "documents": db.query(Document).filter(Document.user_id == current_user.id).count(),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = decode_access_token(credentials.credentials)
    if not payload or payload.get("user_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials.",
        )

    token_id = payload.get("jti")
    expiry = payload.get("exp")
    if not isinstance(token_id, str) or not isinstance(expiry, (int, float)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token cannot be revoked.",
        )

    now = int(time.time())
    db.query(RevokedToken).filter(RevokedToken.expires_at <= now).delete(
        synchronize_session=False
    )
    if db.query(RevokedToken).filter(RevokedToken.jti == token_id).first() is None:
        db.add(RevokedToken(jti=token_id, expires_at=int(expiry)))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
