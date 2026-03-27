from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UploadedFileResponse(BaseModel):
    id: UUID
    kind: str
    file_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime | None


class UploadBatchResponse(BaseModel):
    uploads: list[UploadedFileResponse]
