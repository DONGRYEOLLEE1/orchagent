from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.analytics import ChatTurn, LLMUsageEvent
from services.llm_pricing_service import LLMPricingService


@dataclass(slots=True)
class DashboardSummary:
    user_id: str
    total_turns: int
    completed_turns: int
    total_llm_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_reasoning_tokens: int
    total_cost_microusd: int
    exact_total_cost_microusd: int
    estimated_total_cost_microusd: int
    exact_reasoning_cost_microusd: int
    estimated_reasoning_cost_microusd: int
    avg_latency_ms: int | None
    avg_ttft_ms: int | None
    total_tool_calls: int
    total_inference_cost_microusd: int


@dataclass(slots=True)
class DailyUsagePoint:
    usage_date: date
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int
    total_cost_microusd: int


@dataclass(slots=True)
class LiveTraceRow:
    timestamp: datetime
    user_id: str
    thread_id: str
    turn_id: UUID
    turn_index: int
    request_kind: str
    model: str | None
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency_ms: int | None
    ttft_ms: int | None
    status: str
    active_team_final: str | None


class DashboardService:
    SUPPORTED_REQUEST_KINDS = {"chat", "resume"}

    @staticmethod
    def _as_range(
        start_date: date | None, end_date: date | None
    ) -> tuple[datetime | None, datetime | None]:
        start_at = (
            datetime.combine(start_date, time.min).astimezone()
            if start_date is not None
            else None
        )
        end_at = (
            datetime.combine(end_date + timedelta(days=1), time.min).astimezone()
            if end_date is not None
            else None
        )
        return start_at, end_at

    @staticmethod
    async def _load_turns(
        db: AsyncSession,
        *,
        user_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int | None = None,
    ) -> list[ChatTurn]:
        stmt = select(ChatTurn).where(
            ChatTurn.user_id == user_id,
            ChatTurn.request_kind.in_(DashboardService.SUPPORTED_REQUEST_KINDS),
        )
        if start_at is not None:
            stmt = stmt.where(ChatTurn.started_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(ChatTurn.started_at < end_at)
        stmt = stmt.order_by(ChatTurn.started_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _load_usage_events(
        db: AsyncSession,
        *,
        user_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
        turn_ids: set[UUID] | None = None,
    ) -> list[LLMUsageEvent]:
        stmt = select(LLMUsageEvent).where(LLMUsageEvent.user_id == user_id)
        if start_at is not None:
            stmt = stmt.where(LLMUsageEvent.created_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(LLMUsageEvent.created_at < end_at)
        if turn_ids is not None:
            if not turn_ids:
                return []
            stmt = stmt.where(LLMUsageEvent.turn_id.in_(turn_ids))
        stmt = stmt.order_by(LLMUsageEvent.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _average(values: Iterable[int | None]) -> int | None:
        filtered = [value for value in values if value is not None]
        if not filtered:
            return None
        return int(sum(filtered) / len(filtered))

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        *,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> DashboardSummary:
        start_at, end_at = DashboardService._as_range(start_date, end_date)
        turns = await DashboardService._load_turns(
            db, user_id=user_id, start_at=start_at, end_at=end_at
        )
        usage_events = await DashboardService._load_usage_events(
            db, user_id=user_id, start_at=start_at, end_at=end_at
        )
        recalculated_costs = [
            LLMPricingService.calculate_current_cost_breakdown(
                model=event.model,
                input_tokens=event.input_tokens,
                cache_read_input_tokens=event.cache_read_input_tokens,
                output_tokens=event.output_tokens,
                reasoning_output_tokens=event.reasoning_output_tokens,
            )
            for event in usage_events
        ]

        return DashboardSummary(
            user_id=user_id,
            total_turns=len(turns),
            completed_turns=sum(1 for turn in turns if turn.status == "completed"),
            total_llm_calls=len(usage_events),
            total_input_tokens=sum(event.input_tokens for event in usage_events),
            total_output_tokens=sum(event.output_tokens for event in usage_events),
            total_tokens=sum(event.total_tokens for event in usage_events),
            total_reasoning_tokens=sum(
                event.reasoning_output_tokens for event in usage_events
            ),
            total_cost_microusd=sum(
                cost.total_cost_microusd for cost in recalculated_costs
            ),
            exact_total_cost_microusd=sum(
                cost.total_cost_microusd
                for cost in recalculated_costs
                if not cost.cost_is_estimated
            ),
            estimated_total_cost_microusd=sum(
                cost.total_cost_microusd
                for cost in recalculated_costs
                if cost.cost_is_estimated
            ),
            exact_reasoning_cost_microusd=sum(
                cost.exact_reasoning_cost_microusd for cost in recalculated_costs
            ),
            estimated_reasoning_cost_microusd=sum(
                cost.estimated_reasoning_cost_microusd for cost in recalculated_costs
            ),
            avg_latency_ms=DashboardService._average(
                turn.latency_ms for turn in turns if turn.status == "completed"
            ),
            avg_ttft_ms=DashboardService._average(
                turn.ttft_ms for turn in turns if turn.status == "completed"
            ),
            total_tool_calls=sum(turn.tool_call_count for turn in turns),
            total_inference_cost_microusd=sum(
                cost.total_cost_microusd for cost in recalculated_costs
            ),
        )

    @staticmethod
    async def get_daily_usage_series(
        db: AsyncSession,
        *,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyUsagePoint]:
        start_at, end_at = DashboardService._as_range(start_date, end_date)
        usage_events = await DashboardService._load_usage_events(
            db, user_id=user_id, start_at=start_at, end_at=end_at
        )
        buckets: dict[date, DailyUsagePoint] = {}
        for event in usage_events:
            cost = LLMPricingService.calculate_current_cost_breakdown(
                model=event.model,
                input_tokens=event.input_tokens,
                cache_read_input_tokens=event.cache_read_input_tokens,
                output_tokens=event.output_tokens,
                reasoning_output_tokens=event.reasoning_output_tokens,
            )
            usage_date = event.created_at.date()
            existing = buckets.get(usage_date)
            if existing is None:
                existing = DailyUsagePoint(
                    usage_date=usage_date,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    reasoning_tokens=0,
                    total_cost_microusd=0,
                )
                buckets[usage_date] = existing
            existing.input_tokens += event.input_tokens
            existing.output_tokens += event.output_tokens
            existing.total_tokens += event.total_tokens
            existing.reasoning_tokens += event.reasoning_output_tokens
            existing.total_cost_microusd += cost.total_cost_microusd

        return [buckets[key] for key in sorted(buckets.keys())]

    @staticmethod
    async def get_live_traces(
        db: AsyncSession,
        *,
        user_id: str,
        limit: int = 20,
    ) -> list[LiveTraceRow]:
        turns = await DashboardService._load_turns(
            db,
            user_id=user_id,
            start_at=None,
            end_at=None,
            limit=limit,
        )
        turn_ids = {turn.id for turn in turns}
        usage_events = await DashboardService._load_usage_events(
            db,
            user_id=user_id,
            start_at=None,
            end_at=None,
            turn_ids=turn_ids,
        )
        usage_by_turn: dict[UUID, list[LLMUsageEvent]] = {}
        for event in usage_events:
            usage_by_turn.setdefault(event.turn_id, []).append(event)

        rows: list[LiveTraceRow] = []
        for turn in turns:
            turn_usage = usage_by_turn.get(turn.id, [])
            latest_model = turn_usage[0].model if turn_usage else None
            rows.append(
                LiveTraceRow(
                    timestamp=turn.started_at,
                    user_id=turn.user_id,
                    thread_id=turn.thread_id,
                    turn_id=turn.id,
                    turn_index=turn.turn_index,
                    request_kind=turn.request_kind,
                    model=latest_model,
                    input_tokens=sum(event.input_tokens for event in turn_usage),
                    output_tokens=sum(event.output_tokens for event in turn_usage),
                    reasoning_tokens=sum(
                        event.reasoning_output_tokens for event in turn_usage
                    ),
                    latency_ms=turn.latency_ms,
                    ttft_ms=turn.ttft_ms,
                    status=turn.status,
                    active_team_final=turn.active_team_final,
                )
            )

        return rows
