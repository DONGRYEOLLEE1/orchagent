import uuid
from datetime import datetime

import pytz
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base

KST = pytz.timezone("Asia/Seoul")


class UserMemorySettings(Base):
    __tablename__ = "user_memory_settings"

    user_id = Column(String, ForeignKey("auth_users.id"), primary_key=True)
    memory_enabled = Column(Boolean, nullable=False, default=True)
    instructions_enabled = Column(Boolean, nullable=False, default=True)
    allow_explicit_memory = Column(Boolean, nullable=False, default=True)
    allow_inferred_memory = Column(Boolean, nullable=False, default=True)
    allow_chat_history_reference = Column(Boolean, nullable=False, default=True)
    default_memory_mode = Column(String, nullable=False, default="enabled")
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(KST)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST),
    )


class UserMemoryEntry(Base):
    __tablename__ = "user_memory_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    thread_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=True, index=True
    )
    scope_type = Column(String, nullable=False, default="user_global", index=True)
    source_type = Column(String, nullable=False, default="inferred", index=True)
    status = Column(String, nullable=False, default="active", index=True)
    category = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    content_text = Column(Text, nullable=False)
    content_json = Column(JSONB, nullable=True)
    confidence = Column(Integer, nullable=True)
    salience = Column(Integer, nullable=False, default=0)
    created_from_turn_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_turns.id"), nullable=True, index=True
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST),
        index=True,
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)


class UserPersonalizationInstruction(Base):
    __tablename__ = "user_personalization_instructions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    instruction_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    content_text = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST),
        index=True,
    )


class MemoryReferenceEvent(Base):
    __tablename__ = "memory_reference_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    thread_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    turn_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_turns.id"), nullable=False, index=True
    )
    memory_id = Column(
        UUID(as_uuid=True), ForeignKey("user_memory_entries.id"), nullable=False, index=True
    )
    phase = Column(String, nullable=False, default="retrieval", index=True)
    rank = Column(Integer, nullable=False, default=0)
    reason = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(KST)
    )
