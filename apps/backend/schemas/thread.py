from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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


class ThreadTelemetryResponse(BaseModel):
    thread_id: str
    reasoning_summary: str = ""
    suggested_queries: list[str] = []
