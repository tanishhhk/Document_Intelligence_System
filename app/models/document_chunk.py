from sqlalchemy import Column, String, Integer, Text, ForeignKey, UniqueConstraint
from app.database import Base
import json

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
    )
    
    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Which chunk number (0, 1, 2...)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)  # Stored as JSON string
    
    def set_embedding(self, embedding_list):
        """Convert list to JSON string for storage"""
        self.embedding = json.dumps(embedding_list)
    
    def get_embedding(self):
        """Convert JSON string back to list"""
        return json.loads(self.embedding)
    
    def __repr__(self):
        return f"<DocumentChunk {self.document_id}:{self.chunk_index}>"