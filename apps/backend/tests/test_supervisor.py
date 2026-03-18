import pytest
from typing import cast
from agent_core.supervisor import make_supervisor_node
from agent_core.state import BaseAgentState, build_route_entry
from langchain_core.messages import HumanMessage


class FakeRouterLLM:
    """A Stub LLM that always returns a fixed structured output."""

    def __init__(self, target_node: str):
        self.target_node = target_node

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        # Stub the Pydantic router response
        return {"next": self.target_node}


@pytest.mark.asyncio
async def test_supervisor_routes_to_worker():
    """Test if supervisor returns a Command object routing to the requested worker."""
    fake_llm = FakeRouterLLM("search_agent")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["search_agent", "web_scraper"],
        layer="team",
        team_name="ResearchTeam",
    )

    state = cast(
        BaseAgentState,
        {"messages": [HumanMessage(content="Find me something")], "next": ""},
    )
    command = await supervisor_func(state)

    assert command.goto == "search_agent"
    assert command.update["next"] == "search_agent"
    assert command.update["active_team"] == "research"
    assert command.update["active_worker"] == "search_agent"
    assert command.update["route_history"][0]["layer"] == "team"
    assert command.update["route_history"][0]["team"] == "research"


@pytest.mark.asyncio
async def test_supervisor_routes_to_finish():
    """Test if supervisor translates FINISH to the END node (__end__)."""
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(fake_llm, ["search_agent", "web_scraper"])  # type: ignore

    state = cast(
        BaseAgentState, {"messages": [HumanMessage(content="All done")], "next": ""}
    )
    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["streaming_status"] == "completed"
    assert command.update["active_team"] is None
    assert command.update["active_worker"] is None
    assert command.update["route_history"][0]["next"] == "FINISH"


@pytest.mark.asyncio
async def test_supervisor_routes_to_vision_team():
    """Test if supervisor routes to vision_team when multimodal input is present."""
    # We stub the LLM to return "vision_team"
    fake_llm = FakeRouterLLM("vision_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team"],
    )

    multimodal_content = [
        {"type": "text", "text": "What is in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
    ]
    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content=cast(list, multimodal_content))],
            "next": "",
        },
    )
    command = await supervisor_func(state)

    assert command.goto == "vision_team"
    assert command.update["active_team"] == "vision"
    assert command.update["active_worker"] is None
    assert command.update["streaming_status"] == "running"
    assert command.update["route_history"][0]["team"] == "vision"


@pytest.mark.asyncio
async def test_head_supervisor_routes_complex_finish_to_finalizer():
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Research something and summarize it")],
            "next": "",
            "task_plan": "1. [research_team] Search.\n2. [writing_team] Write.",
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
                    team="writing",
                ),
            ],
        },
    )
    command = await supervisor_func(state)

    assert command.goto == "finalizer"
    assert command.update["streaming_status"] == "running"
    assert command.update["route_history"][0]["next"] == "finalizer"


@pytest.mark.asyncio
async def test_head_supervisor_uses_task_plan_stage_progression():
    fake_llm = FakeRouterLLM("research_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Research and summarize")],
            "next": "",
            "task_plan": "1. [research_team] Search.\n2. [writing_team] Write.",
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="FINISH",
                    team="research",
                )
            ],
        },
    )
    command = await supervisor_func(state)

    assert command.goto == "writing_team"
    assert command.update["active_team"] == "writing"


@pytest.mark.asyncio
async def test_research_team_supervisor_stops_after_dispatch_limit():
    fake_llm = FakeRouterLLM("search_agent")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["search_agent", "web_scraper"],
        layer="team",
        team_name="ResearchTeam",
        max_team_dispatches=5,
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Keep researching")],
            "next": "",
            "shared_context": {"research_dispatch_count": 5},
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="search_agent",
                    team="research",
                    worker="search_agent",
                )
                for _ in range(5)
            ],
        },
    )
    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["route_history"][0]["next"] == "FINISH"
    assert command.update["active_team"] is None
    assert command.update["active_worker"] is None
