import uuid
from datetime import datetime

import pytz
from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base

KST = pytz.timezone("Asia/Seoul")


def _new_id() -> str:
    return str(uuid.uuid4())


class ThreadRepositoryBinding(Base):
    __tablename__ = "thread_repository_bindings"

    id = Column(String, primary_key=True, index=True, default=_new_id)
    thread_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=False, unique=True, index=True
    )
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    source_type = Column(String, nullable=False, index=True)
    source_ref = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    default_branch = Column(String, nullable=True)
    pinned_commit_sha = Column(String, nullable=True)
    uploaded_file_id = Column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=True, index=True
    )
    status = Column(String, nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST),
    )


class WorkspaceJob(Base):
    __tablename__ = "workspace_jobs"

    id = Column(String, primary_key=True, index=True, default=_new_id)
    thread_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    turn_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_turns.id"), nullable=False, index=True
    )
    binding_id = Column(
        String, ForeignKey("thread_repository_bindings.id"), nullable=False, index=True
    )
    workspace_path = Column(String, nullable=False)
    artifact_path = Column(String, nullable=False)
    log_path = Column(String, nullable=False)
    repo_commit_sha = Column(String, nullable=True)
    status = Column(String, nullable=False, default="running", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
    completed_at = Column(DateTime(timezone=True), nullable=True)
