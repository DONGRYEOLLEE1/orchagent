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

    async def fake_build_runtime_payload(db, *, user_id, thread_id):
        assert user_id == "user-1"
        assert thread_id == "thread-1"
        return {
            "personalization": {
                "enabled": True,
                "profile_block": "- 직업: AI Engineer",
                "instructions_block": "- 설명 방식: 추상 개념은 예시와 함께 설명한다",
                "memory_block": "- [personal_interest] 가수 백예린을 굉장히 좋아한다",
                "context_block": "- [personal_interest] 가수 백예린을 굉장히 좋아한다",
            },
            "personalization_meta": {
                "memory_ids": ["00000000-0000-0000-0000-000000000001"],
                "hit_count": 1,
                "active_memory_count": 1,
                "source": "hybrid_personalization",
                "summary_used": True,
                "recent_used": False,
                "cache_hit": False,
                "hit_miss": "hit",
                "context_chars": 32,
                "instruction_ids": ["00000000-0000-0000-0000-000000000010"],
                "instruction_count": 1,
                "instructions_enabled": True,
                "profile_count": 1,
                "response_preference_count": 1,
            },
        }

    monkeypatch.setattr(
        "workflow.load_memories.PersonalizationService.build_runtime_payload",
        fake_build_runtime_payload,
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
        command.update["shared_context"]["personalization"]["profile_block"]
        == "- 직업: AI Engineer"
    )
    assert (
        command.update["shared_context"]["personalization"]["instructions_block"]
        == "- 설명 방식: 추상 개념은 예시와 함께 설명한다"
    )
    assert command.update["shared_context"]["personalization_meta"]["summary_used"] is True
    assert command.update["shared_context"]["personalization_meta"]["retrieval_ms"] >= 0
