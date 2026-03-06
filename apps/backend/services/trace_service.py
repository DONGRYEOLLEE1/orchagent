from sqlalchemy.ext.asyncio import AsyncSession
from models.trace import TraceEvent

class TraceService:
    @staticmethod
    async def create_event(db: AsyncSession, thread_id: str, event_type: str, node_name: str, payload: dict):
        event = TraceEvent(
            thread_id=thread_id,
            event_type=event_type,
            node_name=node_name,
            payload=payload
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
