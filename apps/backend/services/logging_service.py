from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.logging import KST, ChatMessageLog, ChatSession

class LoggingService:
    @staticmethod
    async def get_or_create_session(db: AsyncSession, thread_id: str, user_id: str = None) -> ChatSession:
        result = await db.execute(select(ChatSession).where(ChatSession.id == thread_id))
        session = result.scalar_one_or_none()
        
        if not session:
            session = ChatSession(id=thread_id, user_id=user_id)
            db.add(session)
            await db.flush()
            
        return session

    @staticmethod
    async def log_message(db: AsyncSession, thread_id: str, role: str, content: str) -> ChatMessageLog:
        # Ensure session exists first
        session = await LoggingService.get_or_create_session(db, thread_id)
        session.updated_at = datetime.now(KST)
        
        msg = ChatMessageLog(session_id=thread_id, role=role, content=content)
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg
