from sqlalchemy import Column, DateTime, Integer, String
from datetime import datetime

from app.database import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti = Column(String, primary_key=True)
    expires_at = Column(Integer, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=False, default=datetime.utcnow)
