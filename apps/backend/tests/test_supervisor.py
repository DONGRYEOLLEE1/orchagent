import pytest
from typing import cast
from agent_core.supervisor import make_supervisor_node, requires_human_approval_for_text
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


class ApprovalAwareLLM:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return {
            "next": "writing_team",
            "reasoning": "Need to modify files.",
            "content": "",
            "requires_approval": False,
        }


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
    assert command.update["response_mode"] == "direct"
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
    assert command.update["response_mode"] == "delegated"
    assert command.update["streaming_status"] == "running"
    assert command.update["route_history"][0]["team"] == "vision"


@pytest.mark.asyncio
async def test_head_supervisor_forces_vision_team_before_direct_finish_for_image_turn():
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
    )

    multimodal_content = [
        {"type": "text", "text": "Describe this image."},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
    ]
    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content=cast(list, multimodal_content))],
            "shared_context": {"vision_routed_for_current_turn": False},
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "vision_team"
    assert command.update["active_team"] == "vision"
    assert command.update["response_mode"] == "delegated"
    assert command.update["shared_context"]["vision_routed_for_current_turn"] is True


@pytest.mark.asyncio
async def test_head_supervisor_does_not_loop_back_to_vision_after_vision_turn():
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
    )

    multimodal_content = [
        {"type": "text", "text": "Describe this image."},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
    ]
    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content=cast(list, multimodal_content))],
            "shared_context": {"vision_routed_for_current_turn": True},
            "task_plan": "NO_PLAN",
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["response_mode"] == "direct"


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
    assert command.update["response_mode"] == "finalizer"
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
    assert command.update["response_mode"] == "delegated"


@pytest.mark.asyncio
async def test_head_supervisor_robust_task_plan_regex():
    fake_llm = FakeRouterLLM("research_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
    )

    # Test with variations in task plan formatting
    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Robust test")],
            "next": "",
            "task_plan": "Step 1: [ Research Team ]\nStep 2: [writing_team]",
            "route_history": [],
        },
    )
    command = await supervisor_func(state)

    # Should match [ Research Team ] and normalize it to research_team
    assert command.goto == "research_team"
    assert command.update["active_team"] == "research"
    assert command.update["response_mode"] == "delegated"


@pytest.mark.asyncio
async def test_head_supervisor_clears_content_on_finish_override():
    # LLM wants to answer, but plan says we are done
    class ContentLLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            return {
                "next": "research_team",
                "content": "I should not say this",
                "reasoning": "Looping?",
            }

    supervisor_func = make_supervisor_node(
        ContentLLM(),  # type: ignore
        ["research_team", "writing_team"],
        layer="head",
        final_node_name="finalizer",
        max_team_dispatches=5,
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Done test")],
            "next": "",
            "task_plan": "1. [research_team] Done.",
            "route_history": [
                build_route_entry(
                    layer="team", node="supervisor", next_node="FINISH", team="research"
                )
            ],
        },
    )
    command = await supervisor_func(state)

    # All planned stages are complete -> should override to FINISH (then finalizer)
    assert command.goto == "finalizer"
    assert command.update["response_mode"] == "finalizer"
    # Content should be cleared! In supervisor.py, update_data['messages'] is only set if content is truthy.
    assert "messages" not in command.update or not command.update["messages"]


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


@pytest.mark.asyncio
async def test_head_supervisor_forces_approval_for_filesystem_write_requests(monkeypatch):
    interrupts = []

    def fake_interrupt(payload):
        interrupts.append(payload)
        return {"action": "approve", "feedback": ""}

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    supervisor_func = make_supervisor_node(
        ApprovalAwareLLM(),  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(
                    content="Create a file named hello.txt in the workspace and write hello into it."
                )
            ],
            "next": "",
        },
    )
    command = await supervisor_func(state)

    assert interrupts, "Expected the supervisor to interrupt for approval."
    assert interrupts[0]["goto"] == "writing_team"
    assert command.goto == "writing_team"
    assert command.update["active_team"] == "writing"


@pytest.mark.asyncio
async def test_head_supervisor_forces_approval_for_code_execution_requests(monkeypatch):
    interrupts = []

    def fake_interrupt(payload):
        interrupts.append(payload)
        return {"action": "approve", "feedback": ""}

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    supervisor_func = make_supervisor_node(
        ApprovalAwareLLM(),  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(
                    content="Execute a Python script that writes hello into a file in the current directory."
                )
            ],
            "next": "",
        },
    )
    command = await supervisor_func(state)

    assert interrupts, "Expected the supervisor to interrupt for approval."
    assert interrupts[0]["goto"] == "writing_team"
    assert command.goto == "writing_team"


@pytest.mark.asyncio
async def test_head_supervisor_forces_approval_for_tuple_user_messages(monkeypatch):
    interrupts = []

    def fake_interrupt(payload):
        interrupts.append(payload)
        return {"action": "approve", "feedback": ""}

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    supervisor_func = make_supervisor_node(
        ApprovalAwareLLM(),  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [
                ("user", "Edit the file README.md by adding a phase9 test line.")
            ],
            "next": "",
        },
    )
    command = await supervisor_func(state)

    assert interrupts, "Expected tuple-style user messages to trigger approval."
    assert command.goto == "writing_team"


def test_requires_human_approval_for_text_detects_risky_requests():
    assert requires_human_approval_for_text(
        "Create a file named hello.txt in the workspace."
    )
    assert requires_human_approval_for_text(
        "Execute a Python script that writes to the current directory."
    )
    assert not requires_human_approval_for_text(
        "Summarize the latest AI news in two paragraphs."
    )


@pytest.mark.asyncio
async def test_head_supervisor_forces_approval_from_shared_context_flag(monkeypatch):
    interrupts = []

    def fake_interrupt(payload):
        interrupts.append(payload)
        return {"action": "approve", "feedback": ""}

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    supervisor_func = make_supervisor_node(
        ApprovalAwareLLM(),  # type: ignore
        ["research_team", "writing_team", "vision_team"],
        layer="head",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [("user", "safe text")],
            "shared_context": {"force_requires_approval": True},
            "next": "",
        },
    )
    command = await supervisor_func(state)

    assert interrupts, "Expected shared_context force flag to trigger approval."
    assert command.goto == "writing_team"
    assert command.update["shared_context"]["force_requires_approval"] is False
