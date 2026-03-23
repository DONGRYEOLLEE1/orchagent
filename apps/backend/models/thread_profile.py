import uuid
from datetime import datetime

import pytz
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String

from core.database import Base

KST = pytz.timezone("Asia/Seoul")


def _new_id() -> str:
    return str(uuid.uuid4())


class ThreadProfile(Base):
    __tablename__ = "thread_profiles"

    id = Column(String, primary_key=True, index=True, default=_new_id)
    thread_id = Column(String, ForeignKey("chat_sessions.id"), unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    title_override = Column(String, nullable=True)
    pinned = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST),
    )
