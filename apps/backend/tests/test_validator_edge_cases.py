import pytest
from langchain_core.messages import HumanMessage
from typing import cast

from agent_core.validator import make_validator_node
from agent_core.state import BaseAgentState


class DummyInvalidLLM:
    """Mock LLM always returning is_valid=False to trigger infinite loops (Edge Case 1)"""

    async def ainvoke(self, messages):
        return {"is_valid": False, "reasoning": "Always wrong", "feedback": "Fix this."}

    def with_structured_output(self, schema):
        return self


class DummyExceptionLLM:
    """Mock LLM raising Exception for parsing errors (Edge Case 2)"""

    async def ainvoke(self, messages):
        raise ValueError("Simulated Validation Parsing Error")

    def with_structured_output(self, schema):
        return self


@pytest.mark.asyncio
async def test_validator_edge_case_1_infinite_loop():
    """
    Edge Case 1: 무한 자가 수정 루프 방지 (Infinite Correction Loop)
    Test that when remaining_steps is critically low (<= 1), the validator halts
    the loop and returns a safe fallback message instead of routing for correction.
    """
    validator = make_validator_node(DummyInvalidLLM(), "test_team")  # type: ignore

    # State with 1 remaining step to trigger loop prevention
    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Hello")],
            "remaining_steps": 1,
        },
    )

    command = await validator(state)

    # Check that it routes to supervisor to finish or handle the failure gracefully
    assert command.goto == "supervisor"

    # Check that a fallback warning message is returned
    messages = command.update.get("messages", [])
    assert len(messages) == 1
    assert "[Validation Warning]" in messages[0].content


@pytest.mark.asyncio
async def test_validator_edge_case_2_hallucination():
    """
    Edge Case 2: Validator의 환각 (Validator Hallucination)
    Test that when the Validator's LLM fails to parse structured output (raises an Exception),
    the system catches the error and safely rolls back to the supervisor with an error message.
    """
    validator = make_validator_node(DummyExceptionLLM(), "test_team")  # type: ignore

    # State with sufficient remaining steps
    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Hello")],
            "remaining_steps": 10,
        },
    )

    command = await validator(state)

    # Check that it routes to supervisor to handle the failure gracefully
    assert command.goto == "supervisor"

    # Check that a fallback error message is returned
    messages = command.update.get("messages", [])
    assert len(messages) == 1
    assert "[Validation Error]" in messages[0].content
