from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserMemorySettingsResponse(BaseModel):
    user_id: str
    memory_enabled: bool
    allow_explicit_memory: bool
    allow_inferred_memory: bool
    allow_chat_history_reference: bool
    default_memory_mode: str
    created_at: datetime
    updated_at: datetime


class UserMemorySettingsPatchRequest(BaseModel):
    memory_enabled: bool | None = None
    allow_explicit_memory: bool | None = None
    allow_inferred_memory: bool | None = None
    allow_chat_history_reference: bool | None = None
    default_memory_mode: str | None = Field(default=None, max_length=32)


class PersonalMemoryEntryResponse(BaseModel):
    id: UUID
    user_id: str
    thread_id: str | None
    scope_type: str
    source_type: str
    status: str
    category: str
    title: str
    content_text: str
    confidence: int | None
    salience: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class PersonalMemoryListResponse(BaseModel):
    memories: list[PersonalMemoryEntryResponse]


class PersonalMemoryCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content_text: str = Field(..., min_length=1, max_length=2000)
    category: str = Field(..., min_length=1, max_length=64)
    scope_type: str = Field(default="user_global", max_length=32)
