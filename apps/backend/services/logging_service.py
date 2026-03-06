from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.logging import ChatSession, ChatMessageLog

class LoggingService:
    @staticmethod
    async def get_or_create_session(db: AsyncSession, thread_id: str, user_id: str = None) -> ChatSession:
        result = await db.execute(select(ChatSession).where(ChatSession.id == thread_id))
        session = result.scalar_one_or_none()
        
        if not session:
            session = ChatSession(id=thread_id, user_id=user_id)
            db.add(session)
            await db.commit()
            await db.refresh(session)
            
        return session

    @staticmethod
    async def log_message(db: AsyncSession, thread_id: str, role: str, content: str) -> ChatMessageLog:
        # Ensure session exists first
        await LoggingService.get_or_create_session(db, thread_id)
        
        msg = ChatMessageLog(session_id=thread_id, role=role, content=content)
        db.add(msg)
        await db.commit()
        return msg
