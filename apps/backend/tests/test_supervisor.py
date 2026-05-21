import pytest
from typing import cast
from agent_core.supervisor import make_supervisor_node, requires_human_approval_for_text
from agent_core.state import BaseAgentState, build_route_entry
from langchain_core.messages import AIMessage, HumanMessage


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


class CapturingRouterLLM:
    def __init__(self, next_node: str):
        self.next_node = next_node
        self.captured_messages = None

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.captured_messages = messages
        return {
            "next": self.next_node,
            "reasoning": "captured",
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
    assert command.update["route_history"][0].get("reasoning", "") == ""


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
async def test_head_supervisor_includes_split_personalization_blocks_in_system_prompt():
    fake_llm = CapturingRouterLLM("research_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore[arg-type]
        ["research_team", "writing_team", "vision_team", "data_science_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="최근 LLM 동향을 조사해줘")],
            "shared_context": {
                "personalization": {
                    "enabled": True,
                    "profile_block": "- 직업: AI Engineer",
                    "instructions_block": "- 답변 길이: 기본적으로 간결한 답변을 선호한다",
                    "memory_block": "- [technical_stack] LangGraph와 LangChain을 자주 다룬다",
                }
            },
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "research_team"
    assert fake_llm.captured_messages is not None
    system_prompt = fake_llm.captured_messages[0]["content"]
    assert "USER PERSONALIZATION PROFILE" in system_prompt
    assert "USER RESPONSE PREFERENCES" in system_prompt
    assert "USER MEMORY NOTES" in system_prompt
    assert "The latest user request in the current turn overrides saved personalization." in system_prompt


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
async def test_head_supervisor_keeps_direct_finish_when_content_exists_even_with_prior_team_history():
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
            "messages": [HumanMessage(content="너 이름이 뭐야?")],
            "next": "",
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="FINISH",
                    team="data_science",
                )
            ],
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["response_mode"] == "direct"


@pytest.mark.asyncio
async def test_head_supervisor_overrides_identity_answer_to_orchagent():
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
            "messages": [HumanMessage(content="너 이름이 뭐야?")],
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["response_mode"] == "direct"
    assert command.update["messages"][0].content == "저는 OrchAgent입니다."


@pytest.mark.asyncio
async def test_head_supervisor_prompt_discourages_writing_team_for_simple_research_answer():
    fake_llm = CapturingRouterLLM("research_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore[arg-type]
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="최신 AI 반도체 동향을 조사해서 설명해줘")],
            "next": "",
        },
    )

    await supervisor_func(state)

    assert fake_llm.captured_messages is not None
    system_prompt = fake_llm.captured_messages[0]["content"]
    assert "Do NOT route to `writing_team` by default after `research_team`" in system_prompt


@pytest.mark.asyncio
async def test_team_supervisor_does_not_receive_global_task_plan_prompt():
    fake_llm = CapturingRouterLLM("search_agent")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore[arg-type]
        ["search_agent", "web_scraper"],
        layer="team",
        team_name="ResearchTeam",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Search and summarize RoPE")],
            "next": "",
            "task_plan": "1. [research_team] Search.\n2. [writing_team] Write.",
        },
    )

    await supervisor_func(state)

    assert fake_llm.captured_messages is not None
    system_prompt = fake_llm.captured_messages[0]["content"]
    assert "CURRENT TASK PLAN" not in system_prompt


@pytest.mark.asyncio
async def test_team_supervisor_coerces_invalid_cross_graph_route_to_finish():
    class InvalidTeamLLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            return {
                "next": "head_supervisor",
                "reasoning": "Return to the head supervisor directly.",
                "content": "",
            }

    supervisor_func = make_supervisor_node(
        InvalidTeamLLM(),  # type: ignore[arg-type]
        ["search_agent", "web_scraper"],
        layer="team",
        team_name="ResearchTeam",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="Keep researching")],
            "next": "",
            "task_plan": "1. [research_team] Search.\n2. [writing_team] Write.",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["route_history"][0]["next"] == "FINISH"
    assert command.update["active_team"] is None
    assert command.update["active_worker"] is None


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
