import pytest

from services.memory_agent_service import (
    MemoryAgentService,
    MemoryCandidatePayload,
    MemoryExtractionResult,
)


def test_should_review_message_detects_preference_signal():
    assert (
        MemoryAgentService.should_review_message(
            "난 가수 백예린을 굉장히 좋아해. 대표곡 5개만 뽑아줘."
        )
        is True
    )


def test_should_review_message_returns_false_for_plain_request():
    assert MemoryAgentService.should_review_message("백예린 대표곡 5개만 뽑아줘.") is False


@pytest.mark.asyncio
async def test_extract_candidates_returns_empty_without_signal():
    result = await MemoryAgentService.extract_candidates(
        user_message="백예린 대표곡 5개만 뽑아줘.",
        assistant_message="대표곡 5개를 정리했어.",
    )

    assert result == []


@pytest.mark.asyncio
async def test_extract_candidates_filters_and_normalizes(monkeypatch):
    class FakeAgent:
        async def ainvoke(self, payload):
            assert "Latest user message" in payload["messages"][0]["content"]
            return {
                "structured_response": MemoryExtractionResult(
                    candidates=[
                        MemoryCandidatePayload(
                            category="personal_interest",
                            title="좋아하는 아티스트",
                            content_text="가수 백예린을 좋아한다",
                            scope_type="user_global",
                            confidence=91,
                            salience=88,
                        ),
                        MemoryCandidatePayload(
                            category="personal_interest",
                            title="민감정보",
                            content_text="비밀번호는 1234다",
                            scope_type="user_global",
                            confidence=99,
                            salience=70,
                        ),
                        MemoryCandidatePayload(
                            category="unknown_category",
                            title="무시됨",
                            content_text="무시됨",
                            scope_type="user_global",
                            confidence=95,
                            salience=60,
                        ),
                    ]
                )
            }

    monkeypatch.setattr(MemoryAgentService, "_get_agent", staticmethod(lambda: FakeAgent()))

    result = await MemoryAgentService.extract_candidates(
        user_message="난 가수 백예린을 굉장히 좋아해. 대표곡 5개만 뽑아줘.",
        assistant_message="대표곡 5개를 정리했어.",
    )

    assert len(result) == 1
    assert result[0].category == "personal_interest"
    assert result[0].content_text == "가수 백예린을 좋아한다"


def test_memory_agent_uses_low_reasoning_effort(monkeypatch):
    MemoryAgentService._get_agent.cache_clear()
    captured: dict[str, object] = {}

    def fake_init_chat_model(*, model, model_provider, reasoning):
        captured["model"] = model
        captured["model_provider"] = model_provider
        captured["reasoning"] = reasoning
        return object()

    def fake_create_agent(**kwargs):
        captured["create_agent_kwargs"] = kwargs
        return object()

    monkeypatch.setattr("services.memory_agent_service.init_chat_model", fake_init_chat_model)
    monkeypatch.setattr("services.memory_agent_service.create_agent", fake_create_agent)

    MemoryAgentService._get_agent()

    assert captured["model"] == "gpt-5.4-mini"
    assert captured["reasoning"] == {"effort": "low"}
