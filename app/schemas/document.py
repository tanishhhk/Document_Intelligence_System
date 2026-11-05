from pydantic import BaseModel, ConfigDict
from datetime import datetime

# Schema for document upload response
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_size: int
    upload_date: datetime
    status: str

# Schema for listing all documents
class DocumentList(BaseModel):
    documents: list[DocumentResponse]