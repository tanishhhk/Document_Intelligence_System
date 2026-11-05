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
    error_message: str | None = None
    chunk_count: int | None = None
    page_count: int | None = None
    processed_at: datetime | None = None

# Schema for listing all documents
class DocumentList(BaseModel):
    documents: list[DocumentResponse]


class DocumentPage(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
