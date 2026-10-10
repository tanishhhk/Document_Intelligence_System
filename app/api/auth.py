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
from app.schemas.user import Token, UserCreate, UserLogin, UserResponse
from app.services.auth import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
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
        )
    return user


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    email = str(user_data.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(user_data.password, user.hashed_password):
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
