import pytest
from typing import cast

from agent_core.state import BaseAgentState, build_route_entry
from agent_core.supervisor import make_supervisor_node
from langchain_core.messages import AIMessage, HumanMessage


class FakeRouterLLM:
    def __init__(self, target_node: str):
        self.target_node = target_node

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return {"next": self.target_node}


@pytest.mark.asyncio
async def test_coding_team_supervisor_starts_with_codebase_explorer():
    supervisor = make_supervisor_node(
        FakeRouterLLM("FINISH"),  # type: ignore[arg-type]
        ["codebase_explorer", "implementation_engineer", "runtime_verifier"],
        layer="team",
        team_name="Coding Team",
    )

    state = cast(
        BaseAgentState,
        {"messages": [HumanMessage(content="버그를 수정해줘")], "next": ""},
    )

    command = await supervisor(state)

    assert command.goto == "codebase_explorer"


@pytest.mark.asyncio
async def test_coding_team_supervisor_routes_to_runtime_verifier_when_requested():
    supervisor = make_supervisor_node(
        FakeRouterLLM("FINISH"),  # type: ignore[arg-type]
        ["codebase_explorer", "implementation_engineer", "runtime_verifier"],
        layer="team",
        team_name="Coding Team",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(content="버튼 UI를 수정하고 화면까지 확인해줘"),
                AIMessage(content="[Review Passed] The implementation is materially complete."),
            ],
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="codebase_explorer",
                    team="coding",
                    worker="codebase_explorer",
                ),
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="implementation_engineer",
                    team="coding",
                    worker="implementation_engineer",
                ),
            ],
            "next": "",
        },
    )

    command = await supervisor(state)

    assert command.goto == "runtime_verifier"
