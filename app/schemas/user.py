from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _validate_bcrypt_password_bytes(password: str) -> str:
    # bcrypt considers only up to 72 input bytes; reject longer values instead
    # of silently accepting ambiguous passwords or returning a server error.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes when hashed with bcrypt.")
    return password


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        return _validate_bcrypt_password_bytes(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        return _validate_bcrypt_password_bytes(value)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str
