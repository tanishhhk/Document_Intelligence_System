from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from datetime import datetime
from app.database import Base

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_user_id_upload_date", "user_id", "upload_date"),)
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    upload_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="processing")
    
    def __repr__(self):
        return f"<Document {self.filename}>"