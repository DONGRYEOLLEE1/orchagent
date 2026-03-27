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
