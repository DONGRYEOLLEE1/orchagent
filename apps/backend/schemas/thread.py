from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from schemas.coding import CodingSummary
from schemas.repository import RepositoryBindingResponse


class ThreadSummaryResponse(BaseModel):
    thread_id: str
    title: str
    preview: str
    created_at: datetime | None
    last_activity_at: datetime | None
    message_count: int
    latest_status: str | None
    checkpoint_id: str | None
    pinned: bool = False
    archived: bool = False


class ThreadAttachmentResponse(BaseModel):
    kind: str
    url: str
    alt: str
    file_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None


class ThreadMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime | None
    attachments: list[ThreadAttachmentResponse] = Field(default_factory=list)


class ThreadListResponse(BaseModel):
    threads: list[ThreadSummaryResponse]


class ThreadDetailResponse(BaseModel):
    thread: ThreadSummaryResponse
    messages: list[ThreadMessageResponse]
    repository_binding: RepositoryBindingResponse | None = None
    coding_summary: CodingSummary | None = None


class ThreadTelemetryResponse(BaseModel):
    thread_id: str
    reasoning_summary: str = ""
    suggested_queries: list[str] = []
