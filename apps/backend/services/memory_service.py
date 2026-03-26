from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_memory import MemoryReferenceEvent, UserMemoryEntry, UserMemorySettings
from services.memory_store_service import MemoryStoreService


@dataclass(slots=True)
class PersonalizationContext:
    enabled: bool
    context_block: str
    memory_ids: list[UUID]


@dataclass(slots=True)
class MemoryCandidate:
    category: str
    title: str
    content_text: str
    scope_type: str = "user_global"
    confidence: int | None = None
    salience: int = 0


class MemoryService:
    RETRIEVAL_LIMIT = 8

    @staticmethod
    def _now() -> datetime:
        from models.user_memory import KST

        return datetime.now(KST)

    @staticmethod
    def _collapse_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())

    @staticmethod
    async def get_or_create_settings(
        db: AsyncSession, user_id: str
    ) -> UserMemorySettings:
        result = await db.execute(
            select(UserMemorySettings).where(UserMemorySettings.user_id == user_id)
        )
        settings = result.scalar_one_or_none()
        if settings is not None:
            return settings

        settings = UserMemorySettings(user_id=user_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        return settings

    @staticmethod
    async def update_settings(
        db: AsyncSession,
        *,
        user_id: str,
        memory_enabled: bool | None = None,
        allow_explicit_memory: bool | None = None,
        allow_inferred_memory: bool | None = None,
        allow_chat_history_reference: bool | None = None,
        default_memory_mode: str | None = None,
    ) -> UserMemorySettings:
        settings = await MemoryService.get_or_create_settings(db, user_id)
        if memory_enabled is not None:
            settings.memory_enabled = memory_enabled
        if allow_explicit_memory is not None:
            settings.allow_explicit_memory = allow_explicit_memory
        if allow_inferred_memory is not None:
            settings.allow_inferred_memory = allow_inferred_memory
        if allow_chat_history_reference is not None:
            settings.allow_chat_history_reference = allow_chat_history_reference
        if default_memory_mode is not None:
            settings.default_memory_mode = default_memory_mode

        await db.commit()
        await db.refresh(settings)
        return settings

    @staticmethod
    async def list_memories(
        db: AsyncSession, *, user_id: str, limit: int = 100
    ) -> list[UserMemoryEntry]:
        stmt = (
            select(UserMemoryEntry)
            .where(
                UserMemoryEntry.user_id == user_id,
                UserMemoryEntry.deleted_at.is_(None),
                UserMemoryEntry.status == "active",
            )
            .order_by(desc(UserMemoryEntry.created_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_memory(
        db: AsyncSession,
        *,
        user_id: str,
        title: str,
        content_text: str,
        category: str,
        scope_type: str = "user_global",
        source_type: str = "explicit",
        thread_id: str | None = None,
        confidence: int | None = None,
        salience: int = 0,
        created_from_turn_id: UUID | None = None,
    ) -> UserMemoryEntry:
        memory = UserMemoryEntry(
            user_id=user_id,
            thread_id=thread_id,
            scope_type=scope_type,
            source_type=source_type,
            category=category,
            title=MemoryService._collapse_text(title) or "Personal memory",
            content_text=MemoryService._collapse_text(content_text),
            confidence=confidence,
            salience=salience,
            created_from_turn_id=created_from_turn_id,
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)
        await MemoryStoreService.sync_memory(memory)
        await MemoryStoreService.refresh_summaries_for_user(
            db, user_id=user_id, thread_id=thread_id
        )
        return memory

    @staticmethod
    async def delete_memory(
        db: AsyncSession, *, user_id: str, memory_id: UUID
    ) -> UserMemoryEntry | None:
        result = await db.execute(
            select(UserMemoryEntry).where(
                UserMemoryEntry.id == memory_id,
                UserMemoryEntry.user_id == user_id,
                UserMemoryEntry.deleted_at.is_(None),
            )
        )
        memory = result.scalar_one_or_none()
        if memory is None:
            return None

        memory.status = "deleted"
        memory.deleted_at = MemoryService._now()
        await db.commit()
        await db.refresh(memory)
        await MemoryStoreService.delete_memory(
            user_id=user_id,
            memory_id=memory.id,
            scope_type=memory.scope_type,
            thread_id=memory.thread_id,
        )
        await MemoryStoreService.refresh_summaries_for_user(
            db, user_id=user_id, thread_id=memory.thread_id
        )
        return memory

    @staticmethod
    async def upsert_inferred_memory(
        db: AsyncSession,
        *,
        user_id: str,
        candidate: MemoryCandidate,
        thread_id: str | None,
        created_from_turn_id: UUID | None,
    ) -> tuple[UserMemoryEntry, bool]:
        normalized_title = MemoryService._collapse_text(candidate.title)
        normalized_content = MemoryService._collapse_text(candidate.content_text)
        result = await db.execute(
            select(UserMemoryEntry).where(
                UserMemoryEntry.user_id == user_id,
                UserMemoryEntry.deleted_at.is_(None),
                UserMemoryEntry.status == "active",
                UserMemoryEntry.category == candidate.category,
                UserMemoryEntry.content_text == normalized_content,
                UserMemoryEntry.scope_type == candidate.scope_type,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.confidence = max(
                int(existing.confidence or 0), int(candidate.confidence or 0)
            ) or None
            existing.salience = max(int(existing.salience or 0), int(candidate.salience or 0))
            existing.updated_at = MemoryService._now()
            await db.commit()
            await db.refresh(existing)
            await MemoryStoreService.sync_memory(existing)
            await MemoryStoreService.refresh_summaries_for_user(
                db, user_id=user_id, thread_id=existing.thread_id
            )
            return existing, False

        memory = UserMemoryEntry(
            user_id=user_id,
            thread_id=thread_id if candidate.scope_type == "thread_local" else None,
            scope_type=candidate.scope_type,
            source_type="inferred",
            category=candidate.category,
            title=normalized_title or "Personal memory",
            content_text=normalized_content,
            confidence=candidate.confidence,
            salience=candidate.salience,
            created_from_turn_id=created_from_turn_id,
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)
        await MemoryStoreService.sync_memory(memory)
        await MemoryStoreService.refresh_summaries_for_user(
            db, user_id=user_id, thread_id=memory.thread_id
        )
        return memory, True

    @staticmethod
    async def build_personalization_context(
        db: AsyncSession, *, user_id: str, thread_id: str
    ) -> PersonalizationContext:
        settings = await MemoryService.get_or_create_settings(db, user_id)
        if not settings.memory_enabled or not settings.allow_chat_history_reference:
            return PersonalizationContext(
                enabled=False,
                context_block="",
                memory_ids=[],
            )

        scope_priority = case(
            (UserMemoryEntry.thread_id == thread_id, 0),
            else_=1,
        )
        stmt = (
            select(UserMemoryEntry)
            .where(
                UserMemoryEntry.user_id == user_id,
                UserMemoryEntry.deleted_at.is_(None),
                UserMemoryEntry.status == "active",
                (UserMemoryEntry.thread_id.is_(None))
                | (UserMemoryEntry.thread_id == thread_id),
            )
            .order_by(
                scope_priority,
                desc(UserMemoryEntry.salience),
                desc(UserMemoryEntry.updated_at),
                desc(UserMemoryEntry.created_at),
            )
            .limit(MemoryService.RETRIEVAL_LIMIT)
        )
        result = await db.execute(stmt)
        memories = list(result.scalars().all())
        if not settings.allow_inferred_memory:
            memories = [memory for memory in memories if memory.source_type != "inferred"]

        if not memories:
            return PersonalizationContext(enabled=True, context_block="", memory_ids=[])

        lines = [
            f"- [{memory.category}] {MemoryService._collapse_text(memory.content_text)}"
            for memory in memories
        ]
        return PersonalizationContext(
            enabled=True,
            context_block="\n".join(lines),
            memory_ids=[memory.id for memory in memories],
        )

    @staticmethod
    async def record_reference_events(
        db: AsyncSession,
        *,
        user_id: str,
        thread_id: str,
        turn_id: UUID,
        memory_ids: list[UUID],
        phase: str = "retrieval",
    ) -> None:
        if not memory_ids:
            return

        events = [
            MemoryReferenceEvent(
                user_id=user_id,
                thread_id=thread_id,
                turn_id=turn_id,
                memory_id=memory_id,
                phase=phase,
                rank=index,
                reason="personalization_context",
            )
            for index, memory_id in enumerate(memory_ids, start=1)
        ]
        db.add_all(events)
        await db.commit()
