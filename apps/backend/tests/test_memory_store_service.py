from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

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

    def put(self, namespace, key, value):
        self._summaries[(namespace, key)] = Item(
            namespace=namespace,
            key=key,
            value=value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def delete(self, namespace, key):
        self._summaries.pop((namespace, key), None)


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
    MemoryStoreService._context_cache.clear()
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


def test_build_personalization_payload_marks_cache_hit(monkeypatch):
    MemoryStoreService._context_cache.clear()
    user_id = "user-cache"
    thread_id = "thread-cache"
    global_ns = MemoryStoreService.global_namespace(user_id)
    now = datetime.now(timezone.utc)
    summary = Item(
        namespace=global_ns,
        key="summary",
        value={
            "document_type": "summary",
            "summary_text": "- [tone_style] 간결한 답변을 선호한다",
            "memory_ids": [],
        },
        created_at=now,
        updated_at=now,
    )
    fake_store = FakeStore(items=[], summaries={(global_ns, "summary"): summary})
    monkeypatch.setattr("services.memory_store_service.get_memory_store", lambda: fake_store)

    first = MemoryStoreService.build_personalization_payload(user_id=user_id, thread_id=thread_id)
    second = MemoryStoreService.build_personalization_payload(user_id=user_id, thread_id=thread_id)

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True


def test_build_personalization_payload_prefers_thread_local_memory(monkeypatch):
    MemoryStoreService._context_cache.clear()
    user_id = "user-thread"
    thread_id = "thread-special"
    global_ns = MemoryStoreService.global_namespace(user_id)
    thread_ns = MemoryStoreService.thread_namespace(user_id, thread_id)
    now = datetime.now(timezone.utc)

    thread_summary = Item(
        namespace=thread_ns,
        key="summary",
        value={
            "document_type": "summary",
            "summary_text": "- [ongoing_goal] 이 스레드에서는 백예린 곡만 찾고 있다",
            "memory_ids": [],
        },
        created_at=now,
        updated_at=now,
    )
    global_summary = Item(
        namespace=global_ns,
        key="summary",
        value={
            "document_type": "summary",
            "summary_text": "- [personal_interest] 가수 백예린을 좋아한다",
            "memory_ids": [],
        },
        created_at=now,
        updated_at=now,
    )
    fake_store = FakeStore(
        items=[],
        summaries={
            (thread_ns, "summary"): thread_summary,
            (global_ns, "summary"): global_summary,
        },
    )
    monkeypatch.setattr("services.memory_store_service.get_memory_store", lambda: fake_store)

    payload = MemoryStoreService.build_personalization_payload(
        user_id=user_id,
        thread_id=thread_id,
    )

    lines = payload["context_block"].splitlines()
    assert lines[0] == "- [ongoing_goal] 이 스레드에서는 백예린 곡만 찾고 있다"
    assert lines[1] == "- [personal_interest] 가수 백예린을 좋아한다"


class DummyResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class DummyDb:
    def __init__(self, responses):
        self._responses = list(responses)

    async def execute(self, *_args, **_kwargs):
        return DummyResult(self._responses.pop(0))


import pytest


@pytest.mark.asyncio
async def test_validate_projection_reports_matching_counts(monkeypatch):
    MemoryStoreService._context_cache.clear()
    user_id = "user-validate"
    thread_id = "thread-validate"
    global_ns = MemoryStoreService.global_namespace(user_id)
    thread_ns = MemoryStoreService.thread_namespace(user_id, thread_id)
    now = datetime.now(timezone.utc)
    global_rows = [type("Row", (), {"id": uuid4()})(), type("Row", (), {"id": uuid4()})()]
    thread_rows = [type("Row", (), {"id": uuid4()})()]
    fake_store = FakeStore(
        items=[
            _search_item(global_ns, "g1", str(global_rows[0].id), "g1", now),
            _search_item(global_ns, "g2", str(global_rows[1].id), "g2", now),
            _search_item(thread_ns, "t1", str(thread_rows[0].id), "t1", now),
        ],
        summaries={
            (global_ns, "summary"): Item(
                namespace=global_ns,
                key="summary",
                value={"memory_ids": [str(global_rows[0].id), str(global_rows[1].id)]},
                created_at=now,
                updated_at=now,
            ),
            (thread_ns, "summary"): Item(
                namespace=thread_ns,
                key="summary",
                value={"memory_ids": [str(thread_rows[0].id)]},
                created_at=now,
                updated_at=now,
            ),
        },
    )
    monkeypatch.setattr("services.memory_store_service.get_memory_store", lambda: fake_store)

    validation = await MemoryStoreService.validate_projection(
        DummyDb([global_rows, thread_rows]),
        user_id=user_id,
        thread_id=thread_id,
    )

    assert validation["global_match"] is True
    assert validation["thread_match"] is True
    assert validation["global_summary_count"] == 2
    assert validation["thread_summary_count"] == 1
