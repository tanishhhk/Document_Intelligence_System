from pydantic import BaseModel
from datetime import datetime

# Schema for document upload response
class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_size: int
    upload_date: datetime
    status: str
    
    class Config:
        from_attributes = True

# Schema for listing all documents
class DocumentList(BaseModel):
    documents: list[DocumentResponse]