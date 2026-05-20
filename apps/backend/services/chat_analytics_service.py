from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from core.timezone import now_kst
from models.analytics import ChatTurn, LLMUsageEvent, ToolExecutionEvent


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


@dataclass(slots=True)
class LLMUsageWriteParams:
    user_id: str
    thread_id: str
    turn_id: UUID
    run_id: str | None
    trace_id: str | None
    span_id: str | None
    parent_span_id: str | None
    node_name: str | None
    provider: str
    model: str
    request_role: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_read_input_tokens: int
    cache_write_input_tokens: int
    reasoning_output_tokens: int
    text_output_tokens: int
    usage_metadata: dict
    pricing_snapshot_id: UUID | None = None
    input_cost_microusd: int = 0
    output_cost_microusd: int = 0
    reasoning_cost_microusd: int | None = None
    estimated_reasoning_cost_microusd: int = 0
    total_cost_microusd: int = 0
    cost_is_estimated: bool = False
    reasoning_cost_is_estimated: bool = False
    created_at: datetime | None = None


@dataclass(slots=True)
class ToolExecutionStartParams:
    user_id: str
    thread_id: str
    turn_id: UUID
    run_id: str | None
    trace_id: str | None
    span_id: str | None
    parent_span_id: str | None
    node_name: str | None
    tool_name: str
    display_name: str | None
    started_at: datetime
    input_summary: dict | list | str | None = None


@dataclass(slots=True)
class ToolExecutionFinishParams:
    thread_id: str
    turn_id: UUID
    run_id: str | None
    tool_name: str
    status: str
    ended_at: datetime
    output_summary: dict | list | str | None = None
    error_summary: dict | list | str | None = None


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

    @staticmethod
    async def create_usage_event(
        db: AsyncSession, params: LLMUsageWriteParams
    ) -> LLMUsageEvent:
        usage_event = LLMUsageEvent(
            user_id=params.user_id,
            thread_id=params.thread_id,
            turn_id=params.turn_id,
            run_id=params.run_id,
            trace_id=params.trace_id,
            span_id=params.span_id,
            parent_span_id=params.parent_span_id,
            node_name=params.node_name,
            provider=params.provider,
            model=params.model,
            request_role=params.request_role,
            input_tokens=params.input_tokens,
            output_tokens=params.output_tokens,
            total_tokens=params.total_tokens,
            cache_read_input_tokens=params.cache_read_input_tokens,
            cache_write_input_tokens=params.cache_write_input_tokens,
            reasoning_output_tokens=params.reasoning_output_tokens,
            text_output_tokens=params.text_output_tokens,
            usage_metadata=params.usage_metadata,
            pricing_snapshot_id=params.pricing_snapshot_id,
            input_cost_microusd=params.input_cost_microusd,
            output_cost_microusd=params.output_cost_microusd,
            reasoning_cost_microusd=params.reasoning_cost_microusd,
            estimated_reasoning_cost_microusd=params.estimated_reasoning_cost_microusd,
            total_cost_microusd=params.total_cost_microusd,
            cost_is_estimated=params.cost_is_estimated,
            reasoning_cost_is_estimated=params.reasoning_cost_is_estimated,
            created_at=params.created_at or now_kst(),
        )
        db.add(usage_event)
        await db.commit()
        await db.refresh(usage_event)
        return usage_event

    @staticmethod
    async def create_tool_execution(
        db: AsyncSession, params: ToolExecutionStartParams
    ) -> ToolExecutionEvent:
        tool_event = ToolExecutionEvent(
            user_id=params.user_id,
            thread_id=params.thread_id,
            turn_id=params.turn_id,
            run_id=params.run_id,
            trace_id=params.trace_id,
            span_id=params.span_id,
            parent_span_id=params.parent_span_id,
            node_name=params.node_name,
            tool_name=params.tool_name,
            display_name=params.display_name,
            status="running",
            started_at=params.started_at,
            input_summary=params.input_summary,
        )
        db.add(tool_event)
        await db.commit()
        await db.refresh(tool_event)
        return tool_event

    @staticmethod
    async def finish_tool_execution(
        db: AsyncSession, params: ToolExecutionFinishParams
    ) -> ToolExecutionEvent | None:
        stmt = select(ToolExecutionEvent).where(
            ToolExecutionEvent.thread_id == params.thread_id,
            ToolExecutionEvent.turn_id == params.turn_id,
            ToolExecutionEvent.status == "running",
        )
        if params.run_id is not None:
            stmt = stmt.where(ToolExecutionEvent.run_id == params.run_id)
        else:
            stmt = stmt.where(ToolExecutionEvent.tool_name == params.tool_name)

        result = await db.execute(
            stmt.order_by(ToolExecutionEvent.started_at.desc()).limit(1)
        )
        tool_event = result.scalar_one_or_none()
        if tool_event is None:
            return None

        tool_event.status = params.status
        tool_event.ended_at = params.ended_at
        tool_event.duration_ms = max(
            int((params.ended_at - tool_event.started_at).total_seconds() * 1000), 0
        )
        tool_event.output_summary = params.output_summary
        tool_event.error_summary = params.error_summary

        await db.commit()
        await db.refresh(tool_event)
        return tool_event

    # ---- Fresh-session wrappers (Phase 1.3 — chat-stream sidecar tasks) ----
    @staticmethod
    async def start_turn_with_fresh_session(
        *,
        thread_id: str,
        user_id: str,
        request_kind: str,
        request_message_id: UUID | None,
        started_at: datetime,
        trace_id: str,
        metadata: dict | None = None,
    ) -> ChatTurn:
        async with AsyncSessionLocal() as db:
            return await ChatAnalyticsService.start_turn(
                db,
                ChatTurnStartParams(
                    thread_id=thread_id,
                    user_id=user_id,
                    request_kind=request_kind,
                    request_message_id=request_message_id,
                    started_at=started_at,
                    trace_id=trace_id,
                    metadata=metadata,
                ),
            )

    @staticmethod
    async def mark_first_token_with_fresh_session(
        turn_id: UUID, first_token_at: datetime
    ) -> None:
        async with AsyncSessionLocal() as db:
            await ChatAnalyticsService.mark_first_token(db, turn_id, first_token_at)

    @staticmethod
    async def finalize_turn_with_fresh_session(
        params: ChatTurnFinalizeParams,
    ) -> None:
        async with AsyncSessionLocal() as db:
            await ChatAnalyticsService.finalize_turn(db, params)

    @staticmethod
    async def create_usage_event_with_fresh_session(
        params: LLMUsageWriteParams,
    ) -> None:
        # Import locally to avoid a startup-time cycle with LLMPricingService.
        from services.llm_pricing_service import LLMPricingService

        async with AsyncSessionLocal() as db:
            snapshot = await LLMPricingService.resolve_pricing_snapshot(
                db,
                provider=params.provider,
                model=params.model,
                at=params.created_at or now_kst(),
            )
            priced_params = LLMPricingService.apply_snapshot_to_usage(params, snapshot)
            await ChatAnalyticsService.create_usage_event(db, priced_params)

    @staticmethod
    async def create_tool_execution_with_fresh_session(
        params: ToolExecutionStartParams,
    ) -> None:
        async with AsyncSessionLocal() as db:
            await ChatAnalyticsService.create_tool_execution(db, params)

    @staticmethod
    async def finish_tool_execution_with_fresh_session(
        params: ToolExecutionFinishParams,
    ) -> None:
        async with AsyncSessionLocal() as db:
            await ChatAnalyticsService.finish_tool_execution(db, params)
