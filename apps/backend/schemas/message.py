"""Pydantic response schemas for chat messages.

Phase 1.7 of the codebase-wide refactor. Centralises the on-the-wire shape
of a single chat-message row so the various endpoints that surface message
history (``threads.get_messages``, replay tooling, etc.) share one source
of truth instead of redefining the dict shape inline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MessageAttachmentResponse(BaseModel):
    id: str | None = None
    kind: str | None = None
    url: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None


class MessageResponse(BaseModel):
    """Unified chat-message row."""

    id: UUID
    session_id: str = Field(alias="thread_id")
    role: str
    content: str
    created_at: datetime
    attachments: list[MessageAttachmentResponse] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
