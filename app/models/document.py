from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from datetime import datetime
from app.database import Base

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_user_id_upload_date", "user_id", "upload_date"),
        Index("ix_documents_status_upload_date", "status", "upload_date"),
    )
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    upload_date = Column(DateTime, default=datetime.utcnow)
    # queued, processing, completed or failed; see app.services.ingestion.
    status = Column(String, nullable=False, default="queued")
    error_message = Column(String(500), nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    lease_token = Column(String(36), nullable=True)
    lease_expires_at = Column(Integer, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Document {self.filename}>"