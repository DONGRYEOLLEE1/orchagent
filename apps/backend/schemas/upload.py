from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UploadedFileResponse(BaseModel):
    id: UUID
    input_index: int | None = None
    kind: str
    source_type: str
    processing_status: str
    preview_status: str
    file_name: str
    declared_extension: str | None = None
    mime_type: str
    sniffed_mime_type: str | None = None
    size_bytes: int
    created_at: datetime | None


class UploadErrorResponse(BaseModel):
    input_index: int
    file_name: str
    error_code: str
    detail: str


class UploadBatchResponse(BaseModel):
    uploads: list[UploadedFileResponse]
    errors: list[UploadErrorResponse] = []
    accepted_count: int
    failed_count: int
    total_size_bytes: int
