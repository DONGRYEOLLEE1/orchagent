from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.personalization_service import PersonalizationService


@pytest.mark.asyncio
async def test_build_runtime_payload_merges_instruction_and_memory_blocks(monkeypatch):
    created_at = datetime(2026, 3, 30, 7, 0, 0, tzinfo=timezone.utc)

    async def fake_get_or_create_settings(db, user_id):
        return SimpleNamespace(
            memory_enabled=True,
            instructions_enabled=True,
            allow_chat_history_reference=True,
        )

    async def fake_list_instructions(db, *, user_id, enabled_only=False):
        assert enabled_only is True
        return [
            SimpleNamespace(
                id=uuid4(),
                instruction_type="response_style",
                title="설명 방식",
                content_text="추상 개념은 예시와 함께 설명한다",
                created_at=created_at,
            ),
            SimpleNamespace(
                id=uuid4(),
                instruction_type="user_profile",
                title="직업",
                content_text="AI Engineer",
                created_at=created_at,
            ),
        ]

    async def fake_count_active_memories(db, *, user_id):
        return 2

    monkeypatch.setattr(
        "services.personalization_service.MemoryService.get_or_create_settings",
        fake_get_or_create_settings,
    )
    monkeypatch.setattr(
        "services.personalization_service.PersonalizationInstructionService.list_instructions",
        fake_list_instructions,
    )
    monkeypatch.setattr(
        "services.personalization_service.MemoryService.count_active_memories",
        fake_count_active_memories,
    )
    monkeypatch.setattr(
        "services.personalization_service.MemoryStoreService.build_personalization_payload",
        lambda *, user_id, thread_id: {
            "context_block": "- [technical_stack] LangGraph를 자주 사용한다",
            "memory_ids": [uuid4()],
            "summary_used": True,
            "recent_used": False,
            "cache_hit": False,
        },
    )

    payload = await PersonalizationService.build_runtime_payload(
        db=object(),  # type: ignore[arg-type]
        user_id="user-1",
        thread_id="thread-1",
    )

    assert payload["personalization"]["enabled"] is True
    assert payload["personalization"]["profile_block"] == "- 직업: AI Engineer"
    assert (
        payload["personalization"]["instructions_block"]
        == "- 설명 방식: 추상 개념은 예시와 함께 설명한다"
    )
    assert "LangGraph를 자주 사용한다" in payload["personalization"]["memory_block"]
    assert payload["personalization_meta"]["instruction_count"] == 2
    assert payload["personalization_meta"]["source"] == "hybrid_personalization"


@pytest.mark.asyncio
async def test_build_runtime_payload_returns_instruction_only_source(monkeypatch):
    async def fake_get_or_create_settings(db, user_id):
        return SimpleNamespace(
            memory_enabled=False,
            instructions_enabled=True,
            allow_chat_history_reference=False,
        )

    async def fake_list_instructions(db, *, user_id, enabled_only=False):
        return [
            SimpleNamespace(
                id=uuid4(),
                instruction_type="response_style",
                title="답변 언어",
                content_text="한국어 답변을 선호한다",
            )
        ]

    monkeypatch.setattr(
        "services.personalization_service.MemoryService.get_or_create_settings",
        fake_get_or_create_settings,
    )
    monkeypatch.setattr(
        "services.personalization_service.PersonalizationInstructionService.list_instructions",
        fake_list_instructions,
    )

    payload = await PersonalizationService.build_runtime_payload(
        db=object(),  # type: ignore[arg-type]
        user_id="user-1",
        thread_id="thread-1",
    )

    assert payload["personalization"]["memory_block"] == ""
    assert payload["personalization_meta"]["source"] == "sql_personalization_instructions"
    assert payload["personalization_meta"]["instructions_enabled"] is True
