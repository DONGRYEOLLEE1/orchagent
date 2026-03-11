from sqlalchemy.ext.asyncio import AsyncSession
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
        thread_id: str, event_type: str, node_name: str | None, payload: dict
    ) -> TraceEvent:
        return TraceEvent(
            thread_id=thread_id,
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
        db: AsyncSession, thread_id: str, event_type: str, node_name: str, payload: dict
    ):
        event = TraceService.build_event(
            thread_id=thread_id,
            event_type=event_type,
            node_name=node_name,
            payload=payload,
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
