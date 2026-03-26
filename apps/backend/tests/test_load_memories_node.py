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
    monkeypatch.setattr(
        "workflow.load_memories.MemoryStoreService.build_personalization_context",
        lambda *, user_id, thread_id: (
            "- [personal_interest] 가수 백예린을 굉장히 좋아한다",
            [],
        ),
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
