import pytest

from workflow.load_memories import make_load_memories_node


@pytest.mark.asyncio
async def test_load_memories_node_skips_when_user_missing():
    node = make_load_memories_node()

    command = await node({"shared_context": {"thread_id": "thread-1"}})

    assert command.goto == "planner"


@pytest.mark.asyncio
async def test_load_memories_node_populates_personalization(monkeypatch):
    node = make_load_memories_node()

    async def fake_get_or_create_settings(db, user_id):
        return type(
            "Settings",
            (),
            {
                "memory_enabled": True,
                "allow_chat_history_reference": True,
            },
        )()

    monkeypatch.setattr("workflow.load_memories.MemoryService.get_or_create_settings", fake_get_or_create_settings)
    async def fake_count_active_memories(db, *, user_id):
        return 1

    monkeypatch.setattr(
        "workflow.load_memories.MemoryService.count_active_memories",
        fake_count_active_memories,
    )
    monkeypatch.setattr(
        "workflow.load_memories.MemoryStoreService.build_personalization_payload",
        lambda *, user_id, thread_id: {
            "context_block": "- [personal_interest] 가수 백예린을 굉장히 좋아한다",
            "memory_ids": [],
            "hit_count": 0,
            "summary_used": True,
            "recent_used": False,
            "cache_hit": False,
        },
    )

    command = await node(
        {
            "shared_context": {
                "current_user_id": "user-1",
                "thread_id": "thread-1",
            }
        }
    )

    assert command.goto == "planner"
    assert (
        command.update["shared_context"]["personalization"]["context_block"]
        == "- [personal_interest] 가수 백예린을 굉장히 좋아한다"
    )
    assert command.update["shared_context"]["personalization_meta"]["summary_used"] is True


@pytest.mark.asyncio
async def test_load_memories_node_short_circuits_when_no_active_memory(monkeypatch):
    node = make_load_memories_node()

    async def fake_get_or_create_settings(db, user_id):
        return type(
            "Settings",
            (),
            {
                "memory_enabled": True,
                "allow_chat_history_reference": True,
            },
        )()

    async def fake_count_active_memories(db, *, user_id):
        return 0

    monkeypatch.setattr("workflow.load_memories.MemoryService.get_or_create_settings", fake_get_or_create_settings)
    monkeypatch.setattr("workflow.load_memories.MemoryService.count_active_memories", fake_count_active_memories)

    command = await node(
        {
            "shared_context": {
                "current_user_id": "user-1",
                "thread_id": "thread-1",
            }
        }
    )

    assert command.goto == "planner"
    assert command.update["shared_context"]["personalization_meta"]["source"] == "empty"
    assert command.update["shared_context"]["personalization_meta"]["active_memory_count"] == 0
