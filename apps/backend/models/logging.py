import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base

class ChatSession(Base):
    """Tracks a conversation thread."""
    __tablename__ = "chat_sessions"
    
    id = Column(String, primary_key=True, index=True) # Matches thread_id
    user_id = Column(String, index=True, nullable=True) # For future user auth tracking
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    messages = relationship("ChatMessageLog", back_populates="session", cascade="all, delete-orphan", lazy="selectin")

class ChatMessageLog(Base):
    """Tracks user inputs and final assistant outputs for business metrics."""
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False) # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    session = relationship("ChatSession", back_populates="messages")
