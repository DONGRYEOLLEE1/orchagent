"""Pydantic response schemas for ChatTurn rows.

Phase 1.7 of the codebase-wide refactor. ``ChatTurn`` (models/analytics.py)
previously had no response-side schema — endpoints returned raw dicts or
SQLAlchemy rows. Defining the response shape here lets future endpoints
attach ``response_model=ChatTurnResponse`` for OpenAPI fidelity and makes
the frontend TS types easier to keep in sync.

The chat-stream endpoint itself stays SSE-only (no response_model), so
this schema mostly fronts replay/admin endpoints added in later phases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatTurnResponse(BaseModel):
    """Single chat-turn row as it should be exposed over the API."""

    id: UUID
    thread_id: str
    user_id: str
    request_kind: str = Field(description="'chat' | 'resume' | other future kinds")
    status: str
    started_at: datetime
    finalized_at: datetime | None = None
    first_token_at: datetime | None = None
    trace_id: str | None = None
    error_summary: str | None = None
    metadata: dict[str, Any] | None = None


class ChatTurnSummary(BaseModel):
    """Aggregated counters used by dashboards / replay tooling."""

    turn_id: UUID
    thread_id: str
    started_at: datetime
    duration_ms: int | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_microusd: int = 0
    tool_call_count: int = 0
