from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SchemaPatchService:
    @staticmethod
    async def ensure_trace_event_columns(db: AsyncSession) -> None:
        statements = [
            "ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS user_id VARCHAR",
            "ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS turn_id UUID",
            "ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS seq INTEGER",
            "ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS run_id VARCHAR",
            "ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS trace_id VARCHAR",
            "ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS span_id VARCHAR",
            "ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS parent_span_id VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_trace_events_user_id ON trace_events (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_trace_events_turn_id ON trace_events (turn_id)",
            "CREATE INDEX IF NOT EXISTS ix_trace_events_run_id ON trace_events (run_id)",
            "CREATE INDEX IF NOT EXISTS ix_trace_events_trace_id ON trace_events (trace_id)",
            "CREATE INDEX IF NOT EXISTS ix_trace_events_span_id ON trace_events (span_id)",
            "CREATE INDEX IF NOT EXISTS ix_trace_events_parent_span_id ON trace_events (parent_span_id)",
        ]

        for statement in statements:
            await db.execute(text(statement))

        await db.commit()
