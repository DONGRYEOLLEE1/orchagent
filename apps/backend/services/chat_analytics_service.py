from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.analytics import ChatTurn


@dataclass(slots=True)
class ChatTurnStartParams:
    thread_id: str
    user_id: str
    request_kind: str
    request_message_id: UUID | None
    started_at: datetime
    trace_id: str
    metadata: dict | None = None


@dataclass(slots=True)
class ChatTurnFinalizeParams:
    turn_id: UUID
    status: str
    response_message_id: UUID | None = None
    completed_at: datetime | None = None
    interrupted_at: datetime | None = None
    errored_at: datetime | None = None
    final_checkpoint_id: str | None = None
    final_status_node: str | None = None
    response_mode: str | None = None
    active_team_final: str | None = None
    active_worker_final: str | None = None
    assistant_char_count: int = 0
    tool_call_count: int = 0
    metadata: dict | None = None


class ChatAnalyticsService:
    @staticmethod
    async def start_turn(
        db: AsyncSession, params: ChatTurnStartParams
    ) -> ChatTurn:
        stmt = select(func.max(ChatTurn.turn_index)).where(
            ChatTurn.thread_id == params.thread_id
        )
        if hasattr(db, "scalar"):
            current_max_turn = await db.scalar(stmt)
        else:
            result = await db.execute(stmt)
            current_max_turn = result.scalar_one_or_none()
        turn_id = uuid.uuid4()
        turn = ChatTurn(
            id=turn_id,
            thread_id=params.thread_id,
            user_id=params.user_id,
            turn_index=(current_max_turn or 0) + 1,
            request_message_id=params.request_message_id,
            request_kind=params.request_kind,
            status="running",
            started_at=params.started_at,
            trace_id=params.trace_id or str(turn_id),
            metadata_json=params.metadata,
        )
        db.add(turn)
        await db.commit()
        await db.refresh(turn)
        return turn

    @staticmethod
    async def mark_first_token(
        db: AsyncSession, turn_id: UUID, first_token_at: datetime
    ) -> ChatTurn | None:
        if not hasattr(db, "get"):
            return None
        turn = await db.get(ChatTurn, turn_id)
        if turn is None:
            return None

        if turn.first_token_at is None:
            turn.first_token_at = first_token_at
            turn.ttft_ms = max(
                int((first_token_at - turn.started_at).total_seconds() * 1000), 0
            )
            await db.commit()
            await db.refresh(turn)
        return turn

    @staticmethod
    async def finalize_turn(
        db: AsyncSession, params: ChatTurnFinalizeParams
    ) -> ChatTurn | None:
        if not hasattr(db, "get"):
            return None
        turn = await db.get(ChatTurn, params.turn_id)
        if turn is None:
            return None

        turn.status = params.status
        turn.response_message_id = params.response_message_id
        turn.final_checkpoint_id = params.final_checkpoint_id
        turn.final_status_node = params.final_status_node
        turn.response_mode = params.response_mode
        turn.active_team_final = params.active_team_final
        turn.active_worker_final = params.active_worker_final
        turn.assistant_char_count = params.assistant_char_count
        turn.tool_call_count = params.tool_call_count
        if params.metadata is not None:
            turn.metadata_json = params.metadata

        if params.completed_at is not None:
            turn.completed_at = params.completed_at
            turn.latency_ms = max(
                int((params.completed_at - turn.started_at).total_seconds() * 1000), 0
            )
            if turn.first_token_at is not None and turn.ttft_ms is None:
                turn.ttft_ms = max(
                    int((turn.first_token_at - turn.started_at).total_seconds() * 1000),
                    0,
                )

        if params.interrupted_at is not None:
            turn.interrupted_at = params.interrupted_at

        if params.errored_at is not None:
            turn.errored_at = params.errored_at

        await db.commit()
        await db.refresh(turn)
        return turn
