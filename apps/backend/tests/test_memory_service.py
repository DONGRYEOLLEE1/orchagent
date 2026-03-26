from unittest.mock import AsyncMock

import pytest

from services.memory_service import MemoryService


@pytest.mark.asyncio
async def test_create_memory_records_projection_failure_without_raising(monkeypatch):
    added = []

    class FakeDb:
        def add(self, value):
            added.append(value)

        async def commit(self):
            return None

        async def refresh(self, value):
            value.id = "memory-id"
            value.created_at = value.updated_at = MemoryService._now()
            return None

    trace_events = []

    async def mock_sync_memory(memory):
        raise RuntimeError("projection failed")

    async def mock_refresh_summaries_for_user(*args, **kwargs):
        return None

    async def mock_create_event(db, thread_id, event_type, node_name, payload, **kwargs):
        trace_events.append((thread_id, event_type, node_name, payload))

    monkeypatch.setattr("services.memory_service.MemoryStoreService.sync_memory", mock_sync_memory)
    monkeypatch.setattr(
        "services.memory_service.MemoryStoreService.refresh_summaries_for_user",
        mock_refresh_summaries_for_user,
    )
    monkeypatch.setattr("services.memory_service.TraceService.create_event", mock_create_event)

    memory = await MemoryService.create_memory(
        FakeDb(),
        user_id="user-1",
        thread_id="thread-1",
        title="좋아하는 아티스트",
        content_text="가수 백예린을 좋아한다",
        category="personal_interest",
        created_from_turn_id="turn-1",
    )

    assert memory.title == "좋아하는 아티스트"
    assert trace_events
    assert trace_events[0][1] == "memory_projection_error"
