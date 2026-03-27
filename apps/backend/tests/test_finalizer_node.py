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
    llm = CapturingFinalizerLLM()
    node = make_finalizer_node(llm)  # type: ignore[arg-type]

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(content="두 파일을 분석해줘"),
                AIMessage(content="월별 이익 표\n2026-01 | 40", name="data_analyst"),
                AIMessage(content="[Review Passed] Output materially satisfies the request.", name="data_science_team_reviewer"),
            ],
            "shared_context": {},
        },
    )

    command = await node(state)

    assert command.goto == "__end__"
    assert llm.captured_messages is None
    assert command.update["messages"][0].content == "월별 이익 표\n2026-01 | 40"
