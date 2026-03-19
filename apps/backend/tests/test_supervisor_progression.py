import pytest
from typing import cast

from agent_core.state import BaseAgentState, build_route_entry
from agent_core.supervisor import make_supervisor_node
from langchain_core.messages import HumanMessage


class StaticRouterLLM:
    def __init__(self, next_node: str):
        self.next_node = next_node

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return {"next": self.next_node}


@pytest.mark.asyncio
async def test_head_supervisor_treats_duplicate_completed_team_entries_as_complete():
    supervisor = make_supervisor_node(
        StaticRouterLLM("research_team"),  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Research and summarize RoPE")],
            "next": "",
            "task_plan": "1. [research_team] Research.\n2. [writing_team] Write.",
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="FINISH",
                    team="research",
                ),
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="FINISH",
                    team="research",
                ),
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="FINISH",
                    team="writing",
                ),
            ],
        },
    )

    command = await supervisor(state)

    assert command.goto == "finalizer"
    assert command.update["route_history"][0]["next"] == "finalizer"
