from sqlalchemy.ext.asyncio import AsyncSession
from models.trace import TraceEvent


class TraceService:
    @staticmethod
    def _optimize_payload(payload: dict) -> dict:
        """Truncates large base64 strings in payload to save DB space."""
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
                        and len(v) > 500
                    ):
                        data[k] = v[:100] + "... [BASE64 TRUNCATED]"
                    else:
                        truncate_recursive(v)
            elif isinstance(data, list):
                for i in range(len(data)):
                    if (
                        isinstance(data[i], str)
                        and data[i].startswith("data:image/")
                        and len(data[i]) > 500
                    ):
                        data[i] = data[i][:100] + "... [BASE64 TRUNCATED]"
                    else:
                        truncate_recursive(data[i])

        truncate_recursive(optimized)
        return optimized

    @staticmethod
    async def create_event(
        db: AsyncSession, thread_id: str, event_type: str, node_name: str, payload: dict
    ):
        optimized_payload = TraceService._optimize_payload(payload)
        event = TraceEvent(
            thread_id=thread_id,
            event_type=event_type,
            node_name=node_name,
            payload=optimized_payload,
        )
        db.add(event)
        await db.commit()
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
