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

    @staticmethod
    async def ensure_chat_message_attachment_columns(db: AsyncSession) -> None:
        statements = [
            "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]'::jsonb",
        ]

        for statement in statements:
            await db.execute(text(statement))

        await db.commit()

    @staticmethod
    async def ensure_uploaded_file_columns(db: AsyncSession) -> None:
        statements = [
            "ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS source_type VARCHAR NOT NULL DEFAULT 'device'",
            "ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS processing_status VARCHAR NOT NULL DEFAULT 'ready'",
            "ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS preview_status VARCHAR NOT NULL DEFAULT 'pending'",
            "ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS declared_extension VARCHAR",
            "ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS sniffed_mime_type VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_uploaded_files_source_type ON uploaded_files (source_type)",
            "CREATE INDEX IF NOT EXISTS ix_uploaded_files_processing_status ON uploaded_files (processing_status)",
        ]

        for statement in statements:
            await db.execute(text(statement))

        await db.commit()
