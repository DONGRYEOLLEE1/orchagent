from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from models.trace import TraceEvent


class TraceService:
    TRACE_STRING_LIMIT = 2000
    TRACE_BASE64_LIMIT = 500

    @staticmethod
    def _optimize_payload(payload: dict) -> dict:
        """Truncates large base64 and verbose string payloads to save DB space."""
        import json

        if not payload:
            return payload

        # Create a copy to avoid side effects
        optimized = json.loads(json.dumps(payload))

        def truncate_recursive(data):
            if isinstance(data, dict):
                for k, v in data.items():
                    if (
                        isinstance(v, str)
                        and v.startswith("data:image/")
                        and len(v) > TraceService.TRACE_BASE64_LIMIT
                    ):
                        data[k] = v[:100] + "... [BASE64 TRUNCATED]"
                    elif isinstance(v, str) and len(v) > TraceService.TRACE_STRING_LIMIT:
                        data[k] = v[:500] + "... [TRUNCATED]"
                    else:
                        truncate_recursive(v)
            elif isinstance(data, list):
                for i in range(len(data)):
                    if (
                        isinstance(data[i], str)
                        and data[i].startswith("data:image/")
                        and len(data[i]) > TraceService.TRACE_BASE64_LIMIT
                    ):
                        data[i] = data[i][:100] + "... [BASE64 TRUNCATED]"
                    elif (
                        isinstance(data[i], str)
                        and len(data[i]) > TraceService.TRACE_STRING_LIMIT
                    ):
                        data[i] = data[i][:500] + "... [TRUNCATED]"
                    else:
                        truncate_recursive(data[i])

        truncate_recursive(optimized)
        return optimized

    @staticmethod
    def build_event(
        thread_id: str,
        event_type: str,
        node_name: str | None,
        payload: dict,
        *,
        user_id: str | None = None,
        turn_id=None,
        seq: int | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> TraceEvent:
        return TraceEvent(
            thread_id=thread_id,
            user_id=user_id,
            turn_id=turn_id,
            seq=seq,
            run_id=run_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            event_type=event_type,
            node_name=node_name,
            payload=TraceService._optimize_payload(payload),
        )

    @staticmethod
    async def create_events(db: AsyncSession, events: list[TraceEvent]) -> list[TraceEvent]:
        if not events:
            return []

        db.add_all(events)
        await db.commit()
        return events

    @staticmethod
    async def create_event(
        db: AsyncSession,
        thread_id: str,
        event_type: str,
        node_name: str,
        payload: dict,
        **kwargs,
    ):
        event = TraceService.build_event(
            thread_id=thread_id,
            event_type=event_type,
            node_name=node_name,
            payload=payload,
            **kwargs,
        )
        await TraceService.create_events(db, [event])
        return event

    @staticmethod
    async def get_thread_traces(db: AsyncSession, thread_id: str):
        from sqlalchemy import select

        result = await db.execute(
            select(TraceEvent)
            .where(TraceEvent.thread_id == thread_id)
            .order_by(TraceEvent.created_at.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def persist_events_with_fresh_session(trace_events: list[Any]) -> None:
        if not trace_events:
            return
        async with AsyncSessionLocal() as db:
            await TraceService.create_events(db, trace_events)

    @staticmethod
    async def persist_memory_load_trace_with_fresh_session(
        *,
        user_id: str,
        thread_id: str,
        turn_id: UUID,
        personalization_meta: dict[str, Any],
    ) -> None:
        async with AsyncSessionLocal() as db:
            await TraceService.create_event(
                db,
                thread_id=thread_id,
                event_type="memory_load",
                node_name="load_memories",
                payload={
                    "event_type": "memory_load",
                    "memory_ids": personalization_meta.get("memory_ids", []),
                    "hit_count": personalization_meta.get("hit_count", 0),
                    "active_memory_count": personalization_meta.get(
                        "active_memory_count", 0
                    ),
                    "source": personalization_meta.get("source"),
                    "summary_used": personalization_meta.get("summary_used", False),
                    "recent_used": personalization_meta.get("recent_used", False),
                    "cache_hit": personalization_meta.get("cache_hit", False),
                    "hit_miss": personalization_meta.get("hit_miss", "miss"),
                    "context_chars": personalization_meta.get("context_chars", 0),
                    "retrieval_ms": personalization_meta.get("retrieval_ms", 0),
                    "instruction_ids": personalization_meta.get("instruction_ids", []),
                    "instruction_count": personalization_meta.get("instruction_count", 0),
                    "instructions_enabled": personalization_meta.get(
                        "instructions_enabled", False
                    ),
                    "profile_count": personalization_meta.get("profile_count", 0),
                    "response_preference_count": personalization_meta.get(
                        "response_preference_count", 0
                    ),
                    "thread_id": thread_id,
                },
                user_id=user_id,
                turn_id=turn_id,
            )
