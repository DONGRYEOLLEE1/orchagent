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
async def test_head_supervisor_forces_data_science_team_for_file_analysis_turn():
    fake_llm = FakeRouterLLM("writing_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team", "data_science_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="첨부한 csv 파일 매출 추세를 분석하고 차트로 그려줘")],
            "shared_context": {
                "attachments": [
                    {
                        "id": "upload-1",
                        "kind": "csv",
                        "file_name": "sales.csv",
                        "mime_type": "text/csv",
                        "storage_path": "/tmp/sales.csv",
                    }
                ],
                "data_science_routed_for_current_turn": False,
            },
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "data_science_team"
    assert command.update["active_team"] == "data_science"
    assert command.update["shared_context"]["data_science_routed_for_current_turn"] is True
    assert command.update["route_history"][0]["reasoning"] != ""


@pytest.mark.asyncio
async def test_head_supervisor_does_not_loop_back_to_data_science_team():
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team", "data_science_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="첨부한 csv 파일 분석해줘")],
            "shared_context": {
                "attachments": [
                    {
                        "id": "upload-1",
                        "kind": "csv",
                        "file_name": "sales.csv",
                        "mime_type": "text/csv",
                        "storage_path": "/tmp/sales.csv",
                    }
                ],
                "data_science_routed_for_current_turn": True,
            },
            "task_plan": "NO_PLAN",
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["response_mode"] == "direct"


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
async def test_head_supervisor_does_not_route_attachment_turn_to_research_after_data_science():
    fake_llm = FakeRouterLLM("research_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team", "data_science_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="이 docx 파일 핵심 내용을 요약해줘")],
            "shared_context": {
                "attachments": [
                    {
                        "id": "upload-1",
                        "kind": "docx",
                        "file_name": "notes.docx",
                        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "storage_path": "/tmp/notes.docx",
                    }
                ],
                "data_science_routed_for_current_turn": True,
            },
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["response_mode"] == "direct"


@pytest.mark.asyncio
async def test_head_supervisor_does_not_route_attachment_turn_to_writing_after_data_science():
    fake_llm = FakeRouterLLM("writing_team")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["research_team", "writing_team", "vision_team", "data_science_team"],
        layer="head",
        final_node_name="finalizer",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="이 docx 파일을 요약해줘")],
            "shared_context": {
                "attachments": [
                    {
                        "id": "upload-1",
                        "kind": "docx",
                        "file_name": "notes.docx",
                        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "storage_path": "/tmp/notes.docx",
                    }
                ],
                "data_science_routed_for_current_turn": True,
            },
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"
    assert command.update["response_mode"] == "direct"


@pytest.mark.asyncio
async def test_data_science_team_supervisor_starts_with_data_engineer():
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["data_engineer", "data_analyst"],
        layer="team",
        team_name="Data Science Team",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="첨부 csv 파일을 분석해줘")],
            "route_history": [],
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "data_engineer"
    assert command.update["active_team"] == "data_science"
    assert command.update["active_worker"] == "data_engineer"


@pytest.mark.asyncio
async def test_data_science_team_supervisor_forces_data_analyst_after_engineer():
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["data_engineer", "data_analyst"],
        layer="team",
        team_name="Data Science Team",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [HumanMessage(content="첨부 csv 파일을 분석하고 차트로 보여줘")],
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="data_engineer",
                    team="data_science",
                    worker="data_engineer",
                )
            ],
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "data_analyst"
    assert command.update["active_worker"] == "data_analyst"


@pytest.mark.asyncio
async def test_data_science_team_supervisor_finishes_when_chart_artifact_evidence_exists():
    fake_llm = FakeRouterLLM("data_analyst")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["data_engineer", "data_analyst"],
        layer="team",
        team_name="Data Science Team",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(content="이 csv 파일을 차트로 시각화해줘"),
                AIMessage(content='{"generated_files":["sales_trend_chart.png"],"artifact_count":1}', name="data_analyst"),
            ],
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="data_engineer",
                    team="data_science",
                    worker="data_engineer",
                ),
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="data_analyst",
                    team="data_science",
                    worker="data_analyst",
                ),
            ],
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"


@pytest.mark.asyncio
async def test_data_science_team_supervisor_finishes_after_review_passed_without_chart():
    fake_llm = FakeRouterLLM("data_analyst")
    supervisor_func = make_supervisor_node(
        fake_llm,  # type: ignore
        ["data_engineer", "data_analyst"],
        layer="team",
        team_name="Data Science Team",
    )

    state = cast(
        BaseAgentState,
        {
            "messages": [
                HumanMessage(content="두 csv를 합쳐 월별 이익 표를 만들어줘"),
                AIMessage(content="[Review Passed] Output materially satisfies the request.", name="data_science_team_reviewer"),
            ],
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="data_engineer",
                    team="data_science",
                    worker="data_engineer",
                ),
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="data_analyst",
                    team="data_science",
                    worker="data_analyst",
                ),
            ],
            "next": "",
        },
    )

    command = await supervisor_func(state)

    assert command.goto == "__end__"


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
async def test_head_supervisor_routes_completed_research_only_plan_to_finalizer():
    fake_llm = FakeRouterLLM("FINISH")
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
            "task_plan": "1. [research_team] 필요한 최신 근거를 조사한다.\n2. 최종 답변을 완성한다.",
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

    assert command.goto == "finalizer"
    assert command.update["response_mode"] == "finalizer"
    assert command.update["route_history"][0]["next"] == "finalizer"


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
