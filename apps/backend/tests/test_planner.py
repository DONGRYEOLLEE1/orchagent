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


class RecordingPlannerLLM:
    def __init__(self, plan: str):
        self.plan = plan
        self.called = False

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.called = True
        class Result:
            def __init__(self, plan: str):
                self.plan = plan

        return Result(self.plan)


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
    assert "[writing_team]" not in command.update["task_plan"]
    assert "최종 답변" in command.update["task_plan"]


@pytest.mark.asyncio
async def test_planner_uses_llm_for_explicit_writing_deliverable_request():
    llm = RecordingPlannerLLM(
        "1. [research_team] 자료를 조사한다.\n2. [writing_team] 보고서 초안을 작성한다."
    )
    planner = make_planner_node(llm)  # type: ignore[arg-type]

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(
                    content="웹검색을 통해 RoPE 알고리즘을 조사하고 짧은 보고서로 작성해줘."
                )
            ]
        },
    )

    command = await planner(state)

    assert llm.called is True
    assert command.goto == "head_supervisor"
    assert "[writing_team]" in command.update["task_plan"]
