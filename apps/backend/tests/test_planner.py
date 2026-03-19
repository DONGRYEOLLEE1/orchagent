import pytest
from typing import cast

from agent_core.nodes.planner import make_planner_node
from agent_core.state import BaseAgentState
from langchain_core.messages import HumanMessage


class FailingPlannerLLM:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        raise AssertionError(
            "LLM planner should not run for lightweight research requests"
        )


@pytest.mark.asyncio
async def test_planner_uses_lightweight_plan_for_simple_research_query():
    planner = make_planner_node(FailingPlannerLLM())  # type: ignore

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(
                    content="웹검색을 통해 RoPE 알고리즘에 대해 조사해주고 500자 내외로 설명해줘."
                )
            ]
        },
    )

    command = await planner(state)

    assert command.goto == "head_supervisor"
    assert command.update["task_plan"].count("\n") == 1
    assert "[research_team]" in command.update["task_plan"]
    assert "[writing_team]" in command.update["task_plan"]
