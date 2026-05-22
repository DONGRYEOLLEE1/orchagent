import pytest
from typing import cast

from langchain_core.messages import AIMessage, HumanMessage

from agent_core.nodes.finalizer import make_finalizer_node
from agent_core.state import BaseAgentState


class CapturingFinalizerLLM:
    def __init__(self):
        self.captured_messages = None

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.captured_messages = messages
        return schema_result("final answer")


def schema_result(content: str):
    class Result:
        def __init__(self, value: str):
            self.content = value

    return Result(content)


@pytest.mark.asyncio
async def test_finalizer_deduplicates_consecutive_duplicate_ai_messages():
    """Consecutive identical worker outputs must collapse before reaching the LLM."""
    llm = CapturingFinalizerLLM()
    node = make_finalizer_node(llm)  # type: ignore[arg-type]

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(content="요약해줘"),
                AIMessage(content="same assistant output", name="data_analyst"),
                AIMessage(content="same assistant output", name="data_analyst"),
                AIMessage(content="same assistant output", name="data_analyst"),
            ],
            "shared_context": {},
        },
    )

    command = await node(state)

    assert command.goto == "__end__"
    assert llm.captured_messages is not None
    duplicate_count = sum(
        1
        for message in llm.captured_messages
        if isinstance(message, AIMessage) and message.content == "same assistant output"
    )
    assert duplicate_count == 1


@pytest.mark.asyncio
async def test_finalizer_uses_review_passed_worker_output_without_llm():
    """When a reviewer already approved the output, finalizer must short-circuit
    the LLM call and emit the worker output (flattening structured payloads)."""
    llm = CapturingFinalizerLLM()
    node = make_finalizer_node(llm)  # type: ignore[arg-type]

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(content="두 파일을 분석해줘"),
                AIMessage(
                    content=[
                        {
                            "type": "text",
                            "text": "## 월별 이익(revenue-cost) 표\n| month | profit |\n| 2026-01 | 40 |",
                        }
                    ],
                    name="data_analyst",
                ),
                AIMessage(
                    content="[Review Passed] Output materially satisfies the request.",
                    name="data_science_team_reviewer",
                ),
            ],
            "shared_context": {},
        },
    )

    command = await node(state)

    assert command.goto == "__end__"
    # LLM must not have been invoked.
    assert llm.captured_messages is None
    assert command.update["messages"][0].content == "## 월별 이익(revenue-cost) 표\n| month | profit |\n| 2026-01 | 40 |"


@pytest.mark.asyncio
async def test_finalizer_includes_split_personalization_blocks_in_system_prompt():
    """Finalizer must surface all three personalization blocks + the safety guard."""
    llm = CapturingFinalizerLLM()
    node = make_finalizer_node(llm)  # type: ignore[arg-type]

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(content="다음 응답을 마무리해줘"),
                AIMessage(content="worker output", name="doc_writer"),
            ],
            "shared_context": {
                "personalization": {
                    "enabled": True,
                    "profile_block": "- 직업: AI Engineer",
                    "instructions_block": "- 설명 방식: 추상 개념은 예시와 함께 설명한다",
                    "memory_block": "- [workflow_preference] 구현 전에 구조 비교를 선호한다",
                }
            },
        },
    )

    command = await node(state)

    assert command.goto == "__end__"
    assert llm.captured_messages is not None
    system_prompt = llm.captured_messages[0]["content"]
    assert "USER PERSONALIZATION PROFILE" in system_prompt
    assert "USER RESPONSE PREFERENCES" in system_prompt
    assert "USER MEMORY NOTES" in system_prompt
