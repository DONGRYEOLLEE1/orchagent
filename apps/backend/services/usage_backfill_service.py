from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.timezone import KST
from models.analytics import ChatTurn, LLMUsageEvent
from models.logging import ChatSession
from services.llm_pricing_service import LLMPricingService


@dataclass(slots=True)
class UsageLogEntry:
    user_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    timestamp: datetime


class UsageBackfillService:
    @staticmethod
    def load_usage_log_entries(
        *,
        log_path: str | Path,
        user_id: str,
        before: datetime | None = None,
    ) -> list[UsageLogEntry]:
        path = Path(log_path)
        if not path.exists():
            return []

        entries: list[UsageLogEntry] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get("user_id") != user_id:
                    continue
                timestamp_raw = payload.get("timestamp")
                if not isinstance(timestamp_raw, str):
                    continue
                timestamp = datetime.fromisoformat(timestamp_raw)
                if before is not None and timestamp >= before:
                    continue
                entries.append(
                    UsageLogEntry(
                        user_id=user_id,
                        model=str(payload.get("model") or ""),
                        prompt_tokens=int(payload.get("prompt_tokens") or 0),
                        completion_tokens=int(payload.get("completion_tokens") or 0),
                        total_tokens=int(payload.get("total_tokens") or 0),
                        timestamp=timestamp.astimezone(KST),
                    )
                )

        entries.sort(key=lambda entry: entry.timestamp)
        return entries

    @staticmethod
    async def get_first_exact_usage_at(
        db: AsyncSession,
        *,
        user_id: str,
    ) -> datetime | None:
        result = await db.execute(
            select(LLMUsageEvent)
            .where(LLMUsageEvent.user_id == user_id)
            .order_by(LLMUsageEvent.created_at.asc())
            .limit(1)
        )
        event = result.scalar_one_or_none()
        return event.created_at if event is not None else None

    @staticmethod
    async def _get_or_create_backfill_session(
        db: AsyncSession, *, session_id: str
    ) -> ChatSession:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is not None:
            return session

        session = ChatSession(id=session_id, user_id=None)
        db.add(session)
        await db.flush()
        return session

    @staticmethod
    async def _get_or_create_backfill_turn(
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        usage_date: str,
        started_at: datetime,
        completed_at: datetime,
    ) -> ChatTurn:
        result = await db.execute(
            select(ChatTurn).where(
                ChatTurn.thread_id == session_id,
                ChatTurn.request_kind == "backfill_usage",
            )
        )
        turn = result.scalar_one_or_none()
        if turn is not None:
            turn.started_at = min(turn.started_at, started_at)
            turn.completed_at = max(turn.completed_at or completed_at, completed_at)
            turn.status = "completed"
            turn.metadata_json = {
                "backfill_source": "usage_jsonl",
                "usage_date": usage_date,
                "synthetic": True,
            }
            await db.flush()
            return turn

        turn = ChatTurn(
            id=uuid4(),
            thread_id=session_id,
            user_id=user_id,
            turn_index=1,
            request_kind="backfill_usage",
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=max(int((completed_at - started_at).total_seconds() * 1000), 0),
            ttft_ms=None,
            trace_id=f"backfill:{user_id}:{usage_date}",
            assistant_char_count=0,
            tool_call_count=0,
            metadata_json={
                "backfill_source": "usage_jsonl",
                "usage_date": usage_date,
                "synthetic": True,
            },
        )
        db.add(turn)
        await db.flush()
        return turn

    @staticmethod
    async def backfill_historical_usage_from_log(
        db: AsyncSession,
        *,
        user_id: str,
        log_path: str | Path,
    ) -> int:
        first_exact_usage_at = await UsageBackfillService.get_first_exact_usage_at(
            db, user_id=user_id
        )
        entries = UsageBackfillService.load_usage_log_entries(
            log_path=log_path,
            user_id=user_id,
            before=first_exact_usage_at,
        )
        if not entries:
            return 0

        entries_by_date: dict[str, list[UsageLogEntry]] = {}
        for entry in entries:
            usage_date = entry.timestamp.strftime("%Y-%m-%d")
            entries_by_date.setdefault(usage_date, []).append(entry)

        created_count = 0
        for usage_date, date_entries in entries_by_date.items():
            session_id = f"backfill_usage_{user_id}_{usage_date}"
            await UsageBackfillService._get_or_create_backfill_session(
                db, session_id=session_id
            )
            turn = await UsageBackfillService._get_or_create_backfill_turn(
                db,
                user_id=user_id,
                session_id=session_id,
                usage_date=usage_date,
                started_at=date_entries[0].timestamp,
                completed_at=date_entries[-1].timestamp,
            )

            existing_result = await db.execute(
                select(LLMUsageEvent).where(
                    LLMUsageEvent.turn_id == turn.id,
                    LLMUsageEvent.request_role == "historical_backfill",
                )
            )
            existing_events = existing_result.scalars().all()
            existing_timestamps = {
                str((event.usage_metadata or {}).get("source_timestamp"))
                for event in existing_events
            }

            for entry in date_entries:
                source_timestamp = entry.timestamp.isoformat()
                if source_timestamp in existing_timestamps:
                    continue

                cost = LLMPricingService.calculate_current_cost_breakdown(
                    model=entry.model,
                    input_tokens=entry.prompt_tokens,
                    cache_read_input_tokens=0,
                    output_tokens=entry.completion_tokens,
                    reasoning_output_tokens=0,
                )
                usage_event = LLMUsageEvent(
                    id=uuid4(),
                    user_id=user_id,
                    thread_id=session_id,
                    turn_id=turn.id,
                    run_id=f"backfill:{source_timestamp}",
                    trace_id=turn.trace_id,
                    span_id=f"backfill:{source_timestamp}",
                    parent_span_id=None,
                    node_name="historical_backfill",
                    provider="openai",
                    model=entry.model,
                    request_role="historical_backfill",
                    input_tokens=entry.prompt_tokens,
                    output_tokens=entry.completion_tokens,
                    total_tokens=entry.total_tokens,
                    cache_read_input_tokens=0,
                    cache_write_input_tokens=0,
                    reasoning_output_tokens=0,
                    text_output_tokens=entry.completion_tokens,
                    usage_metadata={
                        "backfill_source": "usage_jsonl",
                        "backfill_kind": "approximate",
                        "source_timestamp": source_timestamp,
                        "synthetic": True,
                    },
                    pricing_snapshot_id=None,
                    input_cost_microusd=cost.input_cost_microusd,
                    output_cost_microusd=cost.output_cost_microusd,
                    reasoning_cost_microusd=(
                        cost.exact_reasoning_cost_microusd or None
                    ),
                    estimated_reasoning_cost_microusd=cost.estimated_reasoning_cost_microusd,
                    total_cost_microusd=cost.total_cost_microusd,
                    cost_is_estimated=cost.cost_is_estimated,
                    reasoning_cost_is_estimated=cost.reasoning_cost_is_estimated,
                    created_at=entry.timestamp,
                )
                db.add(usage_event)
                created_count += 1

        if created_count:
            await db.commit()
        else:
            await db.rollback()
        return created_count
