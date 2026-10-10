from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_size: int
    upload_date: datetime
    status: str


class DocumentList(BaseModel):
    documents: list[DocumentResponse]
