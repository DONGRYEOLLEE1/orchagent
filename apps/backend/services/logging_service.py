from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from models.logging import KST, ChatMessageLog, ChatSession


class LoggingService:
    @staticmethod
    async def get_or_create_session(
        db: AsyncSession, thread_id: str, user_id: str | None = None
    ) -> ChatSession:
        result = await db.execute(select(ChatSession).where(ChatSession.id == thread_id))
        session = result.scalar_one_or_none()

        if not session:
            session = ChatSession(id=thread_id, user_id=user_id)
            db.add(session)
            await db.flush()
        elif user_id is not None:
            if session.user_id is None:
                session.user_id = user_id
            elif session.user_id != user_id:
                raise ValueError("Thread ownership mismatch.")

        return session

    @staticmethod
    async def log_message(
        db: AsyncSession,
        thread_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
        attachments: list[dict[str, str]] | None = None,
    ) -> ChatMessageLog:
        # Ensure session exists first
        session = await LoggingService.get_or_create_session(db, thread_id, user_id)
        session.updated_at = datetime.now(KST)

        msg = ChatMessageLog(
            session_id=thread_id,
            role=role,
            content=content,
            attachments_json=list(attachments or []),
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg

    @staticmethod
    async def update_message_content(
        db: AsyncSession,
        *,
        message_id,
        content: str,
    ) -> None:
        await db.execute(
            update(ChatMessageLog)
            .where(ChatMessageLog.id == message_id)
            .values(content=content)
        )
        await db.commit()

    @staticmethod
    async def log_message_with_fresh_session(
        thread_id: str,
        *,
        role: str,
        content: str,
        user_id: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> ChatMessageLog:
        """Open a fresh AsyncSession and persist a chat message.

        Used by the chat-stream sidecar tasks so that long-running SSE
        generators don't share a single session across cleanup tasks.
        """
        async with AsyncSessionLocal() as db:
            return await LoggingService.log_message(
                db,
                thread_id,
                role=role,
                content=content,
                user_id=user_id,
                attachments=attachments,
            )

    @staticmethod
    async def update_message_content_with_fresh_session(
        *,
        message_id: UUID,
        content: str,
    ) -> None:
        async with AsyncSessionLocal() as db:
            await LoggingService.update_message_content(
                db,
                message_id=message_id,
                content=content,
            )
