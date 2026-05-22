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


class DirectFinishLLM:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return {
            "next": "FINISH",
            "reasoning": "This is a simple direct answer.",
            "content": "저는 OrchAgent입니다.",
            "requires_approval": False,
        }


@pytest.mark.asyncio
async def test_supervisor_routes_to_worker():
    """Routing decision must populate active_team / active_worker / route_history."""
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
    assert command.update["active_team"] == "research"
    assert command.update["active_worker"] == "search_agent"
    assert command.update["route_history"][0]["layer"] == "team"


@pytest.mark.asyncio
async def test_supervisor_routes_to_finish():
    """FINISH at head layer must clear active_team/worker and terminate streaming."""
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


@pytest.mark.asyncio
async def test_head_supervisor_routes_complex_finish_to_finalizer():
    """Multi-team turn FINISH must drop into finalizer, not __end__."""
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prior_history",
    [
        # Regression A (Phase 2.4): no prior team history → direct FINISH with
        # content must emit AIMessage(name="supervisor") and reach __end__.
        [],
        # Regression B: prior team activity must NOT force finalizer when the
        # LLM emitted a direct answer for a follow-up identity question.
        [
            build_route_entry(
                layer="team",
                node="supervisor",
                next_node="FINISH",
                team="data_science",
            )
        ],
    ],
    ids=["no_prior_history", "with_prior_team_history"],
)
async def test_head_supervisor_direct_finish_with_content(prior_history):
    """Direct FINISH with LLM content must (a) go to __end__, (b) emit content
    via AIMessage(name="supervisor"), regardless of prior team history."""
    direct_llm = DirectFinishLLM()
    supervisor_func = make_supervisor_node(
        direct_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team", "data_science_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="한 문장으로 자기소개 해주세요.")],
            "next": "",
            "route_history": prior_history,
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["response_mode"] == "direct"
    assert command.update["messages"][0].content == "저는 OrchAgent입니다."
    assert command.update["messages"][0].name == "supervisor"


@pytest.mark.asyncio
async def test_head_supervisor_forces_approval_from_shared_context_flag(monkeypatch):
    """HITL: shared_context.force_requires_approval must trigger an interrupt before dispatch."""
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
