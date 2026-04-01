from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.analytics import ChatTurn, LLMUsageEvent, ToolExecutionEvent
from models.logging import ChatMessageLog, ChatSession
from models.repository import ThreadRepositoryBinding, WorkspaceJob
from models.trace import TraceEvent
from models.thread_profile import ThreadProfile
from models.user_memory import MemoryReferenceEvent, UserMemoryEntry
from services.thread_profile_service import ThreadProfileService


@dataclass(slots=True)
class ThreadAttachment:
    kind: str
    url: str
    alt: str
    file_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None


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
    attachments: list[ThreadAttachment] = field(default_factory=list)


@dataclass(slots=True)
class ThreadDetail:
    thread: ThreadSummary
    messages: list[ThreadMessage]


@dataclass(slots=True)
class ThreadSuggestionContext:
    user_content: str
    assistant_content: str


@dataclass(slots=True)
class ThreadTitlePolicyStats:
    user_turn_count: int
    assistant_turn_count: int
    ai_title_generation_count: int
    has_manual_title_event: bool


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
    def _build_attachment_url(
        *, thread_id: str, message_id: UUID, attachment_index: int
    ) -> str:
        return (
            f"/api/threads/{thread_id}/messages/{message_id}/attachments/{attachment_index}"
        )

    @staticmethod
    def _build_message_attachments(
        *, thread_id: str, message_id: UUID, attachments_payload: Any
    ) -> list[ThreadAttachment]:
        attachments: list[ThreadAttachment] = []
        for index, attachment in enumerate(attachments_payload or []):
            if not isinstance(attachment, dict):
                continue
            storage_path = attachment.get("storage_path")
            if not isinstance(storage_path, str) or not storage_path:
                continue
            kind = str(attachment.get("kind") or "file")
            file_name = attachment.get("file_name")
            mime_type = attachment.get("mime_type")
            size_bytes = attachment.get("size_bytes")
            attachments.append(
                ThreadAttachment(
                    kind=kind,
                    url=ThreadService._build_attachment_url(
                        thread_id=thread_id,
                        message_id=message_id,
                        attachment_index=index,
                    ),
                    alt=(
                        str(file_name)
                        if isinstance(file_name, str) and file_name
                        else (
                            f"첨부 이미지 {index + 1}"
                            if kind == "image"
                            else f"첨부 파일 {index + 1}"
                        )
                    ),
                    file_name=file_name if isinstance(file_name, str) else None,
                    mime_type=mime_type if isinstance(mime_type, str) else None,
                    size_bytes=size_bytes if isinstance(size_bytes, int) else None,
                )
            )
        return attachments

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
    def _sort_thread_summaries(summaries: list[ThreadSummary]) -> list[ThreadSummary]:
        return sorted(
            summaries,
            key=lambda summary: (
                summary.pinned,
                summary.last_activity_at or summary.created_at or datetime.min,
                summary.created_at or datetime.min,
            ),
            reverse=True,
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
        decorated = [
            ThreadService._apply_profile_overrides(
                summary, profiles.get(summary.thread_id)
            )
            for summary in summaries
        ]
        return ThreadService._sort_thread_summaries(decorated)

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
                ChatMessageLog.attachments_json.label("attachments"),
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
                attachments=ThreadService._build_message_attachments(
                    thread_id=thread_id,
                    message_id=row["id"],
                    attachments_payload=row.get("attachments"),
                ),
            )
            for row in result.mappings().all()
        ]

    @staticmethod
    async def get_thread_message_attachment_path(
        db: AsyncSession,
        *,
        thread_id: str,
        message_id: UUID,
        attachment_index: int,
        user_id: str,
    ) -> str | None:
        session = await ThreadService.get_chat_session(db, thread_id, user_id=user_id)
        if session is None:
            return None

        stmt = (
            select(ChatMessageLog.attachments_json.label("attachments"))
            .where(
                ChatMessageLog.session_id == thread_id,
                ChatMessageLog.id == message_id,
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.mappings().first()
        if row is None:
            return None

        attachments = row.get("attachments") or []
        if attachment_index < 0 or attachment_index >= len(attachments):
            return None

        attachment = attachments[attachment_index]
        if not isinstance(attachment, dict):
            return None

        storage_path = attachment.get("storage_path")
        if not isinstance(storage_path, str) or not storage_path:
            return None

        return storage_path

    @staticmethod
    async def get_latest_user_attachments(
        db: AsyncSession, *, thread_id: str, user_id: str
    ) -> list[dict[str, Any]]:
        session = await ThreadService.get_chat_session(db, thread_id, user_id=user_id)
        if session is None:
            return []

        stmt = (
            select(ChatMessageLog.attachments_json.label("attachments"))
            .where(
                ChatMessageLog.session_id == thread_id,
                ChatMessageLog.role == "user",
                func.jsonb_array_length(ChatMessageLog.attachments_json) > 0,
            )
            .order_by(ChatMessageLog.created_at.desc(), ChatMessageLog.id.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.mappings().first()
        if row is None:
            return []

        attachments = row.get("attachments") or []
        return [attachment for attachment in attachments if isinstance(attachment, dict)]

    @staticmethod
    async def get_latest_suggestion_context(
        db: AsyncSession, thread_id: str
    ) -> ThreadSuggestionContext | None:
        assistant_stmt = (
            select(
                ChatMessageLog.content.label("content"),
                ChatMessageLog.created_at.label("created_at"),
                ChatMessageLog.id.label("id"),
            )
            .where(
                ChatMessageLog.session_id == thread_id,
                ChatMessageLog.role == "assistant",
            )
            .order_by(ChatMessageLog.created_at.desc(), ChatMessageLog.id.desc())
            .limit(1)
        )
        assistant_result = await db.execute(assistant_stmt)
        assistant_row = assistant_result.mappings().first()
        if assistant_row is None:
            return None

        user_stmt = (
            select(ChatMessageLog.content.label("content"))
            .where(
                ChatMessageLog.session_id == thread_id,
                ChatMessageLog.role == "user",
                ChatMessageLog.created_at <= assistant_row["created_at"],
                ~ChatMessageLog.content.like("[User Action]:%"),
            )
            .order_by(ChatMessageLog.created_at.desc(), ChatMessageLog.id.desc())
            .limit(1)
        )
        user_result = await db.execute(user_stmt)
        user_row = user_result.mappings().first()
        if user_row is None:
            return None

        return ThreadSuggestionContext(
            user_content=user_row["content"],
            assistant_content=assistant_row["content"],
        )

    @staticmethod
    async def get_thread_title_policy_stats(
        db: AsyncSession, thread_id: str
    ) -> ThreadTitlePolicyStats:
        user_turn_stmt = (
            select(func.count(ChatMessageLog.id))
            .where(
                ChatMessageLog.session_id == thread_id,
                ChatMessageLog.role == "user",
                ~ChatMessageLog.content.like("[User Action]:%"),
            )
        )
        assistant_turn_stmt = (
            select(func.count(ChatMessageLog.id))
            .where(
                ChatMessageLog.session_id == thread_id,
                ChatMessageLog.role == "assistant",
            )
        )
        ai_generation_stmt = (
            select(func.count(TraceEvent.id))
            .where(
                TraceEvent.thread_id == thread_id,
                TraceEvent.event_type == "thread_title_ai_generated",
            )
        )
        manual_title_stmt = (
            select(func.count(TraceEvent.id))
            .where(
                TraceEvent.thread_id == thread_id,
                TraceEvent.event_type == "thread_title_manual",
            )
        )

        user_turn_result = await db.execute(user_turn_stmt)
        assistant_turn_result = await db.execute(assistant_turn_stmt)
        ai_generation_result = await db.execute(ai_generation_stmt)
        manual_title_result = await db.execute(manual_title_stmt)

        return ThreadTitlePolicyStats(
            user_turn_count=int(user_turn_result.scalar_one() or 0),
            assistant_turn_count=int(assistant_turn_result.scalar_one() or 0),
            ai_title_generation_count=int(ai_generation_result.scalar_one() or 0),
            has_manual_title_event=bool(manual_title_result.scalar_one() or 0),
        )

    @staticmethod
    async def get_thread_message_role_counts(
        db: AsyncSession, thread_id: str
    ) -> dict[str, int]:
        stmt = (
            select(
                ChatMessageLog.role.label("role"),
                func.count(ChatMessageLog.id).label("count"),
            )
            .where(ChatMessageLog.session_id == thread_id)
            .group_by(ChatMessageLog.role)
        )
        result = await db.execute(stmt)
        counts = {row["role"]: row["count"] for row in result.mappings().all()}
        return {
            "user": int(counts.get("user", 0) or 0),
            "assistant": int(counts.get("assistant", 0) or 0),
        }

    @staticmethod
    async def get_thread_detail(
        db: AsyncSession, thread_id: str, *, user_id: str
    ) -> ThreadDetail | None:
        thread = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
        if thread is None:
            return None

        messages = await ThreadService.get_thread_messages(db, thread_id)
        return ThreadDetail(thread=thread, messages=messages)

    @staticmethod
    async def delete_thread(
        db: AsyncSession, thread_id: str, *, user_id: str
    ) -> bool:
        session = await ThreadService.get_chat_session(db, thread_id, user_id=user_id)
        if session is None:
            return False

        turn_ids_stmt = select(ChatTurn.id).where(ChatTurn.thread_id == thread_id)
        turn_ids_result = await db.execute(turn_ids_stmt)
        turn_ids = list(turn_ids_result.scalars().all())

        await db.execute(
            delete(ThreadProfile).where(
                ThreadProfile.thread_id == thread_id,
                ThreadProfile.user_id == user_id,
            )
        )
        await db.execute(
            delete(WorkspaceJob).where(WorkspaceJob.thread_id == thread_id)
        )
        await db.execute(
            delete(ThreadRepositoryBinding).where(
                ThreadRepositoryBinding.thread_id == thread_id,
                ThreadRepositoryBinding.user_id == user_id,
            )
        )
        await db.execute(
            delete(MemoryReferenceEvent).where(MemoryReferenceEvent.thread_id == thread_id)
        )
        await db.execute(
            update(UserMemoryEntry)
            .where(UserMemoryEntry.thread_id == thread_id)
            .values(thread_id=None)
        )
        if turn_ids:
            await db.execute(
                update(UserMemoryEntry)
                .where(UserMemoryEntry.created_from_turn_id.in_(turn_ids))
                .values(created_from_turn_id=None)
            )
            await db.execute(
                delete(LLMUsageEvent).where(LLMUsageEvent.turn_id.in_(turn_ids))
            )
            await db.execute(
                delete(ToolExecutionEvent).where(ToolExecutionEvent.turn_id.in_(turn_ids))
            )
            await db.execute(
                delete(TraceEvent).where(TraceEvent.turn_id.in_(turn_ids))
            )
        await db.execute(delete(TraceEvent).where(TraceEvent.thread_id == thread_id))
        await db.execute(delete(LLMUsageEvent).where(LLMUsageEvent.thread_id == thread_id))
        await db.execute(
            delete(ToolExecutionEvent).where(ToolExecutionEvent.thread_id == thread_id)
        )
        await db.execute(delete(ChatTurn).where(ChatTurn.thread_id == thread_id))
        await db.delete(session)
        await db.commit()
        return True
