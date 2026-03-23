import secrets
import uuid
from datetime import datetime

import pytz
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from core.database import Base

KST = pytz.timezone("Asia/Seoul")


def _new_id() -> str:
    return str(uuid.uuid4())


def _new_public_token() -> str:
    return secrets.token_urlsafe(32)


class AuthUser(Base):
    __tablename__ = "auth_users"

    id = Column(String, primary_key=True, index=True, default=_new_id)
    login_id = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String, nullable=False, default="user", index=True)
    status = Column(String, nullable=False, default="active", index=True)
    must_change_password = Column(Boolean, nullable=False, default=False)
    display_name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST),
    )

    sessions = relationship(
        "AuthSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(String, primary_key=True, index=True, default=_new_id)
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    session_token_hash = Column(String, unique=True, index=True, nullable=False)
    csrf_token_hash = Column(String, nullable=False)
    public_id = Column(String, unique=True, index=True, nullable=False, default=_new_public_token)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("AuthUser", back_populates="sessions", lazy="selectin")
