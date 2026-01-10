from pydantic import BaseModel, EmailStr
from datetime import datetime

# Schema for user registration (what user sends)
class UserCreate(BaseModel):
    email: EmailStr
    password: str

# Schema for user login (what user sends)
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Schema for user response (what we send back)
class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime
    
    class Config:
        from_attributes = True

# Schema for token response (after login)
class Token(BaseModel):
    access_token: str
    token_type: str