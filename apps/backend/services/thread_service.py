from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.logging import ChatMessageLog, ChatSession
from models.trace import TraceEvent
from services.thread_profile_service import ThreadProfileService


@dataclass(slots=True)
class ThreadSummary:
    thread_id: str
    title: str
    preview: str
    created_at: datetime | None
    last_activity_at: datetime | None
    message_count: int
    latest_status: str | None
    checkpoint_id: str | None
    pinned: bool
    archived: bool


@dataclass(slots=True)
class ThreadMessage:
    id: UUID
    role: str
    content: str
    created_at: datetime | None


@dataclass(slots=True)
class ThreadDetail:
    thread: ThreadSummary
    messages: list[ThreadMessage]


class ThreadService:
    DEFAULT_LIMIT = 50
    TITLE_MAX_LENGTH = 80
    PREVIEW_MAX_LENGTH = 140
    UNTITLED_THREAD = "Untitled chat"

    @staticmethod
    def _collapse_text(content: str | None) -> str:
        if not content:
            return ""
        return " ".join(content.split())

    @staticmethod
    def _truncate(content: str, limit: int) -> str:
        normalized = ThreadService._collapse_text(content)
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    @staticmethod
    def _derive_title(first_user_content: str | None) -> str:
        if not first_user_content:
            return ThreadService.UNTITLED_THREAD
        return ThreadService._truncate(first_user_content, ThreadService.TITLE_MAX_LENGTH)

    @staticmethod
    def _derive_preview(
        latest_assistant_content: str | None, latest_user_content: str | None
    ) -> str:
        preview_source = latest_assistant_content or latest_user_content or ""
        return ThreadService._truncate(preview_source, ThreadService.PREVIEW_MAX_LENGTH)

    @staticmethod
    def _derive_status(
        latest_status: str | None, checkpoint_status: str | None
    ) -> str | None:
        return latest_status or checkpoint_status

    @staticmethod
    def _build_summary(row: dict[str, Any]) -> ThreadSummary:
        return ThreadSummary(
            thread_id=row["thread_id"],
            title=ThreadService._derive_title(row.get("first_user_content")),
            preview=ThreadService._derive_preview(
                row.get("latest_assistant_content"), row.get("latest_user_content")
            ),
            created_at=row.get("created_at"),
            last_activity_at=row.get("last_activity_at") or row.get("created_at"),
            message_count=row.get("message_count") or 0,
            latest_status=ThreadService._derive_status(
                row.get("latest_status"), row.get("checkpoint_status")
            ),
            checkpoint_id=row.get("checkpoint_id"),
            pinned=False,
            archived=False,
        )

    @staticmethod
    def _apply_profile_overrides(
        summary: ThreadSummary, profile: Any | None
    ) -> ThreadSummary:
        if profile is None:
            return summary

        return ThreadSummary(
            thread_id=summary.thread_id,
            title=profile.title_override or summary.title,
            preview=summary.preview,
            created_at=summary.created_at,
            last_activity_at=summary.last_activity_at,
            message_count=summary.message_count,
            latest_status=summary.latest_status,
            checkpoint_id=summary.checkpoint_id,
            pinned=profile.pinned,
            archived=profile.archived,
        )

    @staticmethod
    def _thread_summary_stmt(*, thread_id: str | None = None, limit: int | None = None):
        last_message_at = (
            select(func.max(ChatMessageLog.created_at))
            .where(ChatMessageLog.session_id == ChatSession.id)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        first_user_content = (
            select(ChatMessageLog.content)
            .where(
                ChatMessageLog.session_id == ChatSession.id,
                ChatMessageLog.role == "user",
            )
            .order_by(ChatMessageLog.created_at.asc(), ChatMessageLog.id.asc())
            .limit(1)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        latest_assistant_content = (
            select(ChatMessageLog.content)
            .where(
                ChatMessageLog.session_id == ChatSession.id,
                ChatMessageLog.role == "assistant",
            )
            .order_by(ChatMessageLog.created_at.desc(), ChatMessageLog.id.desc())
            .limit(1)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        latest_user_content = (
            select(ChatMessageLog.content)
            .where(
                ChatMessageLog.session_id == ChatSession.id,
                ChatMessageLog.role == "user",
            )
            .order_by(ChatMessageLog.created_at.desc(), ChatMessageLog.id.desc())
            .limit(1)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        message_count = (
            select(func.count(ChatMessageLog.id))
            .where(ChatMessageLog.session_id == ChatSession.id)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        latest_status = (
            select(TraceEvent.payload.op("->>")("status"))
            .where(
                TraceEvent.thread_id == ChatSession.id,
                TraceEvent.event_type == "status",
            )
            .order_by(TraceEvent.created_at.desc(), TraceEvent.id.desc())
            .limit(1)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        latest_checkpoint_id = (
            select(TraceEvent.payload.op("->>")("checkpoint_id"))
            .where(
                TraceEvent.thread_id == ChatSession.id,
                TraceEvent.event_type == "checkpoint",
            )
            .order_by(TraceEvent.created_at.desc(), TraceEvent.id.desc())
            .limit(1)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        latest_checkpoint_status = (
            select(TraceEvent.payload.op("->>")("streaming_status"))
            .where(
                TraceEvent.thread_id == ChatSession.id,
                TraceEvent.event_type == "checkpoint",
            )
            .order_by(TraceEvent.created_at.desc(), TraceEvent.id.desc())
            .limit(1)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        last_activity_at = func.coalesce(
            last_message_at, ChatSession.updated_at, ChatSession.created_at
        )

        stmt = (
            select(
                ChatSession.id.label("thread_id"),
                ChatSession.created_at.label("created_at"),
                last_activity_at.label("last_activity_at"),
                message_count.label("message_count"),
                first_user_content.label("first_user_content"),
                latest_assistant_content.label("latest_assistant_content"),
                latest_user_content.label("latest_user_content"),
                latest_status.label("latest_status"),
                latest_checkpoint_id.label("checkpoint_id"),
                latest_checkpoint_status.label("checkpoint_status"),
            )
            .order_by(desc(last_activity_at), ChatSession.created_at.desc())
        )

        if thread_id is not None:
            stmt = stmt.where(ChatSession.id == thread_id)
        if limit is not None:
            stmt = stmt.limit(limit)

        return stmt

    @staticmethod
    async def get_chat_session(
        db: AsyncSession, thread_id: str, *, user_id: str | None = None
    ) -> ChatSession | None:
        stmt = select(ChatSession).where(ChatSession.id == thread_id)
        if user_id is not None:
            stmt = stmt.where(ChatSession.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_thread_summaries(
        db: AsyncSession, *, user_id: str, limit: int = DEFAULT_LIMIT
    ) -> list[ThreadSummary]:
        stmt = ThreadService._thread_summary_stmt(limit=limit).where(
            ChatSession.user_id == user_id
        )

        result = await db.execute(stmt)
        summaries = [
            ThreadService._build_summary(dict(row))
            for row in result.mappings().all()
        ]
        profiles = await ThreadProfileService.get_thread_profiles_map(
            db,
            [summary.thread_id for summary in summaries],
            user_id,
        )
        return [
            ThreadService._apply_profile_overrides(
                summary, profiles.get(summary.thread_id)
            )
            for summary in summaries
        ]

    @staticmethod
    async def get_thread_summary(
        db: AsyncSession, thread_id: str, *, user_id: str
    ) -> ThreadSummary | None:
        stmt = ThreadService._thread_summary_stmt(thread_id=thread_id, limit=1).where(
            ChatSession.user_id == user_id
        )
        result = await db.execute(stmt)
        row = result.mappings().first()
        if row is None:
            return None
        summary = ThreadService._build_summary(dict(row))
        profile = await ThreadProfileService.get_thread_profile(db, thread_id, user_id)
        return ThreadService._apply_profile_overrides(summary, profile)

    @staticmethod
    async def get_thread_messages(
        db: AsyncSession, thread_id: str
    ) -> list[ThreadMessage]:
        stmt = (
            select(
                ChatMessageLog.id.label("id"),
                ChatMessageLog.role.label("role"),
                ChatMessageLog.content.label("content"),
                ChatMessageLog.created_at.label("created_at"),
            )
            .where(ChatMessageLog.session_id == thread_id)
            .order_by(ChatMessageLog.created_at.asc(), ChatMessageLog.id.asc())
        )
        result = await db.execute(stmt)
        return [
            ThreadMessage(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in result.mappings().all()
        ]

    @staticmethod
    async def get_thread_detail(
        db: AsyncSession, thread_id: str, *, user_id: str
    ) -> ThreadDetail | None:
        thread = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
        if thread is None:
            return None

        messages = await ThreadService.get_thread_messages(db, thread_id)
        return ThreadDetail(thread=thread, messages=messages)
