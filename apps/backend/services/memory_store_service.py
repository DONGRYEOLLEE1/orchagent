from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory_store import get_memory_store
from models.user_memory import UserMemoryEntry


class MemoryStoreService:
    SUMMARY_KEY = "summary"
    RECENT_LIMIT = 5
    SEARCH_FETCH_LIMIT = 20
    MAX_CONTEXT_CHARS = 1200
    CACHE_TTL_SECONDS = 15.0
    _context_cache: dict[
        tuple[str, str],
        tuple[float, dict[str, Any]],
    ] = {}

    @staticmethod
    def global_namespace(user_id: str) -> tuple[str, ...]:
        return ("users", user_id, "memory", "global")

    @staticmethod
    def thread_namespace(user_id: str, thread_id: str) -> tuple[str, ...]:
        return ("users", user_id, "memory", "thread", thread_id)

    @staticmethod
    def _memory_key(memory_id: UUID) -> str:
        return str(memory_id)

    @staticmethod
    def _collapse_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())

    @staticmethod
    def _document_from_memory(memory: UserMemoryEntry) -> dict[str, Any]:
        return {
            "document_type": "memory",
            "memory_id": str(memory.id),
            "category": memory.category,
            "title": memory.title,
            "content_text": memory.content_text,
            "scope_type": memory.scope_type,
            "source_type": memory.source_type,
            "salience": int(memory.salience or 0),
            "confidence": int(memory.confidence or 0) if memory.confidence is not None else None,
            "status": memory.status,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
        }

    @staticmethod
    def _namespace_for_memory(memory: UserMemoryEntry) -> tuple[str, ...]:
        if memory.scope_type == "thread_local" and memory.thread_id:
            return MemoryStoreService.thread_namespace(memory.user_id, memory.thread_id)
        return MemoryStoreService.global_namespace(memory.user_id)

    @staticmethod
    def invalidate_context_cache(*, user_id: str, thread_id: str | None = None) -> None:
        keys_to_remove = []
        for cache_key in MemoryStoreService._context_cache:
            cached_user_id, cached_thread_id = cache_key
            if cached_user_id != user_id:
                continue
            if thread_id is None or cached_thread_id == thread_id:
                keys_to_remove.append(cache_key)
        for key in keys_to_remove:
            MemoryStoreService._context_cache.pop(key, None)

    @staticmethod
    async def sync_memory(memory: UserMemoryEntry) -> None:
        store = get_memory_store()
        if store is None:
            return
        store.put(
            MemoryStoreService._namespace_for_memory(memory),
            MemoryStoreService._memory_key(memory.id),
            MemoryStoreService._document_from_memory(memory),
        )
        MemoryStoreService.invalidate_context_cache(
            user_id=memory.user_id,
            thread_id=memory.thread_id,
        )

    @staticmethod
    async def delete_memory(
        *, user_id: str, memory_id: UUID, scope_type: str, thread_id: str | None
    ) -> None:
        store = get_memory_store()
        if store is None:
            return
        namespace = (
            MemoryStoreService.thread_namespace(user_id, thread_id)
            if scope_type == "thread_local" and thread_id
            else MemoryStoreService.global_namespace(user_id)
        )
        store.delete(namespace, str(memory_id))
        MemoryStoreService.invalidate_context_cache(user_id=user_id, thread_id=thread_id)

    @staticmethod
    async def _build_summary_document(
        db: AsyncSession,
        *,
        user_id: str,
        scope_type: str,
        thread_id: str | None = None,
    ) -> dict[str, Any] | None:
        stmt = (
            select(UserMemoryEntry)
            .where(
                UserMemoryEntry.user_id == user_id,
                UserMemoryEntry.deleted_at.is_(None),
                UserMemoryEntry.status == "active",
                UserMemoryEntry.scope_type == scope_type,
            )
            .order_by(desc(UserMemoryEntry.updated_at), desc(UserMemoryEntry.created_at))
            .limit(MemoryStoreService.RECENT_LIMIT)
        )
        if scope_type == "thread_local":
            stmt = stmt.where(UserMemoryEntry.thread_id == thread_id)
        else:
            stmt = stmt.where(UserMemoryEntry.thread_id.is_(None))

        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        if not rows:
            return None

        lines = [f"- [{row.category}] {MemoryStoreService._collapse_text(row.content_text)}" for row in rows]
        return {
            "document_type": "summary",
            "scope_type": scope_type,
            "thread_id": thread_id,
            "summary_text": "\n".join(lines),
            "memory_ids": [str(row.id) for row in rows],
            "updated_at": max(row.updated_at for row in rows).isoformat(),
        }

    @staticmethod
    async def refresh_summaries_for_user(
        db: AsyncSession, *, user_id: str, thread_id: str | None = None
    ) -> None:
        store = get_memory_store()
        if store is None:
            return

        global_namespace = MemoryStoreService.global_namespace(user_id)
        global_doc = await MemoryStoreService._build_summary_document(
            db, user_id=user_id, scope_type="user_global"
        )
        if global_doc is None:
            store.delete(global_namespace, MemoryStoreService.SUMMARY_KEY)
        else:
            store.put(global_namespace, MemoryStoreService.SUMMARY_KEY, global_doc)

        if thread_id:
            thread_namespace = MemoryStoreService.thread_namespace(user_id, thread_id)
            thread_doc = await MemoryStoreService._build_summary_document(
                db,
                user_id=user_id,
                scope_type="thread_local",
                thread_id=thread_id,
            )
            if thread_doc is None:
                store.delete(thread_namespace, MemoryStoreService.SUMMARY_KEY)
            else:
                store.put(thread_namespace, MemoryStoreService.SUMMARY_KEY, thread_doc)

        MemoryStoreService.invalidate_context_cache(user_id=user_id, thread_id=thread_id)

    @staticmethod
    async def backfill_active_memories(db: AsyncSession) -> None:
        store = get_memory_store()
        if store is None:
            return

        result = await db.execute(
            select(UserMemoryEntry).where(
                UserMemoryEntry.deleted_at.is_(None),
                UserMemoryEntry.status == "active",
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            await MemoryStoreService.sync_memory(row)

        user_threads: dict[str, set[str]] = {}
        for row in rows:
            if row.thread_id:
                user_threads.setdefault(row.user_id, set()).add(row.thread_id)

        for user_id in {row.user_id for row in rows}:
            await MemoryStoreService.refresh_summaries_for_user(db, user_id=user_id)
        for user_id, thread_ids in user_threads.items():
            for thread_id in thread_ids:
                await MemoryStoreService.refresh_summaries_for_user(
                    db, user_id=user_id, thread_id=thread_id
                )

    @staticmethod
    def _dedupe_recent_items(items: list[Any]) -> list[Any]:
        seen: set[str] = set()
        ordered: list[Any] = []
        for item in sorted(items, key=lambda item: item.updated_at, reverse=True):
            memory_id = str(item.value.get("memory_id") or item.key)
            if memory_id in seen:
                continue
            seen.add(memory_id)
            ordered.append(item)
            if len(ordered) >= MemoryStoreService.RECENT_LIMIT:
                break
        return ordered

    @staticmethod
    def _compute_personalization_payload(
        *, user_id: str, thread_id: str
    ) -> dict[str, Any]:
        store = get_memory_store()
        if store is None:
            return {
                "context_block": "",
                "memory_ids": [],
                "hit_count": 0,
                "summary_used": False,
                "recent_used": False,
                "cache_hit": False,
            }

        global_ns = MemoryStoreService.global_namespace(user_id)
        thread_ns = MemoryStoreService.thread_namespace(user_id, thread_id)

        lines: list[str] = []
        memory_ids: list[UUID] = []
        summary_used = False
        recent_used = False

        thread_summary = store.get(thread_ns, MemoryStoreService.SUMMARY_KEY)
        global_summary = store.get(global_ns, MemoryStoreService.SUMMARY_KEY)
        if thread_summary and thread_summary.value.get("summary_text"):
            summary_used = True
            lines.append(str(thread_summary.value["summary_text"]).strip())
            memory_ids.extend(
                UUID(memory_id) for memory_id in thread_summary.value.get("memory_ids", [])
            )
        if global_summary and global_summary.value.get("summary_text"):
            summary_used = True
            lines.append(str(global_summary.value["summary_text"]).strip())
            memory_ids.extend(
                UUID(memory_id) for memory_id in global_summary.value.get("memory_ids", [])
            )

        recent_items = MemoryStoreService._dedupe_recent_items(
            [
                *store.search(
                    thread_ns,
                    filter={"document_type": "memory", "status": "active"},
                    limit=MemoryStoreService.SEARCH_FETCH_LIMIT,
                ),
                *store.search(
                    global_ns,
                    filter={"document_type": "memory", "status": "active"},
                    limit=MemoryStoreService.SEARCH_FETCH_LIMIT,
                ),
            ]
        )
        for item in recent_items:
            content_text = MemoryStoreService._collapse_text(item.value.get("content_text"))
            category = MemoryStoreService._collapse_text(item.value.get("category"))
            if not content_text:
                continue
            recent_used = True
            lines.append(f"- [{category}] {content_text}")
            memory_id = item.value.get("memory_id")
            if memory_id:
                try:
                    memory_ids.append(UUID(str(memory_id)))
                except ValueError:
                    pass

        deduped_lines: list[str] = []
        seen_lines: set[str] = set()
        current_length = 0
        for block in lines:
            for line in block.splitlines():
                normalized = MemoryStoreService._collapse_text(line)
                if not normalized or normalized in seen_lines:
                    continue
                if current_length + len(normalized) + 1 > MemoryStoreService.MAX_CONTEXT_CHARS:
                    break
                seen_lines.add(normalized)
                deduped_lines.append(normalized)
                current_length += len(normalized) + 1

        unique_memory_ids: list[UUID] = []
        seen_ids: set[UUID] = set()
        for memory_id in memory_ids:
            if memory_id in seen_ids:
                continue
            seen_ids.add(memory_id)
            unique_memory_ids.append(memory_id)

        return {
            "context_block": "\n".join(deduped_lines),
            "memory_ids": unique_memory_ids,
            "hit_count": len(unique_memory_ids),
            "summary_used": summary_used,
            "recent_used": recent_used,
            "cache_hit": False,
        }

    @staticmethod
    def build_personalization_payload(
        *, user_id: str, thread_id: str
    ) -> dict[str, Any]:
        cache_key = (user_id, thread_id)
        cached = MemoryStoreService._context_cache.get(cache_key)
        now_mono = time.monotonic()
        if cached is not None:
            expires_at, payload = cached
            if now_mono < expires_at:
                return {
                    **payload,
                    "cache_hit": True,
                }
            MemoryStoreService._context_cache.pop(cache_key, None)

        payload = MemoryStoreService._compute_personalization_payload(
            user_id=user_id,
            thread_id=thread_id,
        )
        MemoryStoreService._context_cache[cache_key] = (
            now_mono + MemoryStoreService.CACHE_TTL_SECONDS,
            payload,
        )
        return payload

    @staticmethod
    def build_personalization_context(
        *, user_id: str, thread_id: str
    ) -> tuple[str, list[UUID]]:
        payload = MemoryStoreService.build_personalization_payload(
            user_id=user_id,
            thread_id=thread_id,
        )
        return payload["context_block"], payload["memory_ids"]

    @staticmethod
    async def validate_projection(
        db: AsyncSession, *, user_id: str, thread_id: str | None = None
    ) -> dict[str, Any]:
        store = get_memory_store()
        if store is None:
            return {
                "store_available": False,
                "sql_global_count": 0,
                "store_global_count": 0,
                "global_summary_count": 0,
                "thread_sql_count": 0,
                "thread_store_count": 0,
                "thread_summary_count": 0,
                "global_match": False,
                "thread_match": False,
            }

        global_result = await db.execute(
            select(UserMemoryEntry).where(
                UserMemoryEntry.user_id == user_id,
                UserMemoryEntry.thread_id.is_(None),
                UserMemoryEntry.deleted_at.is_(None),
                UserMemoryEntry.status == "active",
            )
        )
        sql_global_rows = list(global_result.scalars().all())
        global_ns = MemoryStoreService.global_namespace(user_id)
        global_store_rows = store.search(
            global_ns,
            filter={"document_type": "memory", "status": "active"},
            limit=1000,
        )
        global_summary = store.get(global_ns, MemoryStoreService.SUMMARY_KEY)

        thread_sql_rows: list[UserMemoryEntry] = []
        thread_store_rows: list[Any] = []
        thread_summary_count = 0
        if thread_id:
            thread_result = await db.execute(
                select(UserMemoryEntry).where(
                    UserMemoryEntry.user_id == user_id,
                    UserMemoryEntry.thread_id == thread_id,
                    UserMemoryEntry.deleted_at.is_(None),
                    UserMemoryEntry.status == "active",
                )
            )
            thread_sql_rows = list(thread_result.scalars().all())
            thread_ns = MemoryStoreService.thread_namespace(user_id, thread_id)
            thread_store_rows = store.search(
                thread_ns,
                filter={"document_type": "memory", "status": "active"},
                limit=1000,
            )
            thread_summary = store.get(thread_ns, MemoryStoreService.SUMMARY_KEY)
            thread_summary_count = len(thread_summary.value.get("memory_ids", [])) if thread_summary else 0

        global_summary_count = (
            len(global_summary.value.get("memory_ids", []))
            if global_summary and global_summary.value
            else 0
        )
        return {
            "store_available": True,
            "sql_global_count": len(sql_global_rows),
            "store_global_count": len(global_store_rows),
            "global_summary_count": global_summary_count,
            "thread_sql_count": len(thread_sql_rows),
            "thread_store_count": len(thread_store_rows),
            "thread_summary_count": thread_summary_count,
            "global_match": len(sql_global_rows) == len(global_store_rows),
            "thread_match": (not thread_id) or (len(thread_sql_rows) == len(thread_store_rows)),
        }
