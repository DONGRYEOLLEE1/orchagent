from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import UUID

from langgraph.store.base import Item, SearchItem

from services.memory_store_service import MemoryStoreService


class FakeStore:
    def __init__(self, items, summaries):
        self._items = items
        self._summaries = summaries

    def get(self, namespace, key):
        return self._summaries.get((namespace, key))

    def search(self, namespace_prefix, *, query=None, filter=None, limit=10, offset=0, refresh_ttl=None):
        rows = [
            item
            for item in self._items
            if item.namespace == namespace_prefix
            and all(item.value.get(k) == v for k, v in (filter or {}).items())
        ]
        return rows[:limit]


def _search_item(namespace, key, memory_id, content_text, updated_at):
    return SearchItem(
        namespace=namespace,
        key=key,
        value={
            "document_type": "memory",
            "memory_id": memory_id,
            "category": "personal_interest",
            "content_text": content_text,
            "status": "active",
        },
        created_at=updated_at,
        updated_at=updated_at,
        score=None,
    )


def test_build_personalization_context_uses_summary_and_latest_five(monkeypatch):
    user_id = "user-1"
    thread_id = "thread-2"
    global_ns = MemoryStoreService.global_namespace(user_id)
    thread_ns = MemoryStoreService.thread_namespace(user_id, thread_id)
    now = datetime.now(timezone.utc)

    summary = Item(
        namespace=global_ns,
        key="summary",
        value={
            "document_type": "summary",
            "summary_text": "- [personal_interest] 가수 백예린을 굉장히 좋아한다",
            "memory_ids": ["00000000-0000-0000-0000-000000000001"],
        },
        created_at=now,
        updated_at=now,
    )
    items = [
        _search_item(global_ns, f"k{i}", f"00000000-0000-0000-0000-00000000000{i+1}", f"memory-{i}", now + timedelta(minutes=i))
        for i in range(7)
    ]
    fake_store = FakeStore(items=items, summaries={(global_ns, "summary"): summary})
    monkeypatch.setattr("services.memory_store_service.get_memory_store", lambda: fake_store)

    block, ids = MemoryStoreService.build_personalization_context(
        user_id=user_id,
        thread_id=thread_id,
    )

    assert "가수 백예린을 굉장히 좋아한다" in block
    assert "memory-6" in block
    assert "memory-5" in block
    assert "memory-1" not in block
    assert len(ids) >= 5

