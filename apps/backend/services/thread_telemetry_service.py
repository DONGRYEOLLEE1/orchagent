from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trace import TraceEvent


@dataclass(slots=True)
class ThreadTelemetry:
    reasoning_summary: str
    suggested_queries: list[str]


class ThreadTelemetryService:
    @staticmethod
    async def _get_latest_trace_payload(
        db: AsyncSession, thread_id: str, event_type: str
    ) -> dict | None:
        result = await db.execute(
            select(TraceEvent.payload)
            .where(
                TraceEvent.thread_id == thread_id,
                TraceEvent.event_type == event_type,
            )
            .order_by(TraceEvent.created_at.desc(), TraceEvent.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _normalize_suggested_queries(value: object) -> list[str]:
        if not isinstance(value, list):
            return []

        suggestions: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                continue
            normalized = " ".join(item.split()).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            suggestions.append(normalized)
        return suggestions

    @staticmethod
    async def get_thread_telemetry(
        db: AsyncSession, thread_id: str
    ) -> ThreadTelemetry:
        reasoning_payload = await ThreadTelemetryService._get_latest_trace_payload(
            db, thread_id, "reasoning_summary"
        )
        suggestions_payload = await ThreadTelemetryService._get_latest_trace_payload(
            db, thread_id, "suggested_queries_summary"
        )

        reasoning_summary = ""
        if isinstance(reasoning_payload, dict):
            reasoning_summary = str(reasoning_payload.get("content") or "").strip()

        suggested_queries: list[str] = []
        if isinstance(suggestions_payload, dict):
            suggested_queries = ThreadTelemetryService._normalize_suggested_queries(
                suggestions_payload.get("suggested_queries")
            )

        return ThreadTelemetry(
            reasoning_summary=reasoning_summary,
            suggested_queries=suggested_queries,
        )
