from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base


class UploadIdempotency(Base):
    __tablename__ = "upload_idempotency"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_upload_key_per_user"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String, nullable=False)
    document_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="processing")
    expires_at = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
