import json
from fastapi.testclient import TestClient
from main import app
from services.trace_service import TraceService
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from agent_core.state import BaseAgentState, build_route_entry

client = TestClient(app)


def _sse_payloads(response):
    payloads = []
    for line in response.iter_lines():
        if line and line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    return payloads


def test_health_check():
    """Health check endpoint should return 200 OK."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "OrchAgent backend is running.",
    }


def test_chat_stream_emits_normalized_events(monkeypatch):
    """Graph/raw LangGraph events should be normalized to the frontend SSE contract."""

    class MockSaver:
        async def setup(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "test_123",
                "checkpoint_id": "cp-1",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": ["a", "b"],
            "route_history": [1, 2],
            "streaming_status": "completed",
        }
        next = ()
        created_at = "2026-03-11T00:00:00+00:00"

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "data": {
                    "output": Command(
                        update={
                            "active_team": "research",
                            "active_worker": None,
                            "streaming_status": "running",
                            "route_history": [
                                build_route_entry(
                                    layer="head",
                                    node="head_supervisor",
                                    next_node="research_team",
                                    team="research",
                                    status="running",
                                )
                            ],
                        },
                        goto="research_team",
                    )
                },
            }
            yield {
                "event": "on_tool_start",
                "name": "tavily_tool",
                "data": {"input": {"query": "latest ai news"}},
                "run_id": "tool-1",
            }
            yield {
                "event": "on_tool_end",
                "name": "tavily_tool",
                "data": {"output": {"results": 3}},
                "run_id": "tool-1",
            }
            chunk = AIMessageChunk(content="hello")
            yield {
                "event": "on_chat_model_stream",
                "name": "search",
                "data": {"chunk": chunk},
                "run_id": "model-1",
            }
            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "data": {
                    "output": Command(
                        update={
                            "active_team": None,
                            "active_worker": None,
                            "streaming_status": "completed",
                            "route_history": [
                                build_route_entry(
                                    layer="head",
                                    node="head_supervisor",
                                    next_node="FINISH",
                                    status="completed",
                                )
                            ],
                        },
                        goto="__end__",
                    )
                },
            }

        async def aget_state(self, config, subgraphs=False):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: MockGraph()})(),
    )

    persisted_batches = []

    async def mock_create_events(*args, **kwargs):
        persisted_batches.append(args[1])
        return args[1]

    monkeypatch.setattr(TraceService, "create_events", mock_create_events)

    async def mock_log_message(*args, **kwargs):
        pass

    from services.logging_service import LoggingService

    monkeypatch.setattr(LoggingService, "log_message", mock_log_message)

    with client.stream(
        "POST", "/api/chat", json={"message": "hello", "thread_id": "test_123"}
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert [payload["event_type"] for payload in payloads] == [
        "status",
        "route",
        "status",
        "tool_start",
        "tool_end",
        "text",
        "route",
        "status",
        "checkpoint",
    ]
    assert payloads[0]["status"] == "running"
    assert payloads[1]["target"] == "research_team"
    assert payloads[2]["active_team"] == "research"
    assert payloads[3]["tool_name"] == "tavily_tool"
    assert payloads[5]["content"] == "hello"
    assert payloads[7]["status"] == "completed"
    assert payloads[8]["checkpoint_id"] == "cp-1"
    assert len(persisted_batches) == 1
    assert all(event.event_type != "text" for event in persisted_batches[0])


def test_chat_stream_direct_supervisor_response_uses_same_text_contract(monkeypatch):
    class MockSaver:
        async def setup(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "direct_1",
                "checkpoint_id": "cp-direct",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": ["user", "assistant"],
            "route_history": [],
            "streaming_status": "completed",
        }
        next = ()
        created_at = "2026-03-11T00:00:00+00:00"

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "data": {
                    "output": Command(
                        update={
                            "messages": [AIMessage(content="hello from supervisor")],
                            "active_team": None,
                            "active_worker": None,
                            "streaming_status": "completed",
                            "route_history": [
                                build_route_entry(
                                    layer="head",
                                    node="head_supervisor",
                                    next_node="FINISH",
                                    status="completed",
                                )
                            ],
                        },
                        goto="__end__",
                    )
                },
            }

        async def aget_state(self, config, subgraphs=False):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: MockGraph()})(),
    )

    async def mock_create_events(*args, **kwargs):
        return []

    monkeypatch.setattr(TraceService, "create_events", mock_create_events)

    async def mock_log_message(*args, **kwargs):
        pass

    from services.logging_service import LoggingService

    monkeypatch.setattr(LoggingService, "log_message", mock_log_message)

    with client.stream(
        "POST", "/api/chat", json={"message": "hello", "thread_id": "direct_1"}
    ) as response:
        payloads = _sse_payloads(response)

    assert any(payload["event_type"] == "text" for payload in payloads)
    assert any(
        payload["event_type"] == "text"
        and "hello from supervisor" in payload["content"]
        for payload in payloads
    )


def test_chat_stream_resume_same_thread_id_restores_checkpoint_state(monkeypatch):
    class MockSaver:
        async def setup(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())

    async def mock_create_events(*args, **kwargs):
        return []

    monkeypatch.setattr(TraceService, "create_events", mock_create_events)

    async def mock_log_message(*args, **kwargs):
        pass

    from services.logging_service import LoggingService

    monkeypatch.setattr(LoggingService, "log_message", mock_log_message)

    checkpointer = InMemorySaver()

    def head_supervisor(state: BaseAgentState):
        turn_count = sum(
            1 for msg in state["messages"] if getattr(msg, "type", "") == "human"
        )
        return Command(
            update={
                "messages": [AIMessage(content=f"turn:{turn_count}")],
                "streaming_status": "completed",
                "shared_context": {"turn_count": turn_count},
                "route_history": [
                    build_route_entry(
                        layer="head",
                        node="head_supervisor",
                        next_node="FINISH",
                        status="completed",
                    )
                ],
            },
            goto=END,
        )

    builder = StateGraph(BaseAgentState)  # type: ignore
    builder.add_node("head_supervisor", head_supervisor)
    builder.add_edge(START, "head_supervisor")
    compiled_graph = builder.compile(checkpointer=checkpointer)

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: compiled_graph})(),
    )

    with client.stream(
        "POST", "/api/chat", json={"message": "first", "thread_id": "resume_1"}
    ) as response:
        first_payloads = _sse_payloads(response)

    with client.stream(
        "POST", "/api/chat", json={"message": "second", "thread_id": "resume_1"}
    ) as response:
        second_payloads = _sse_payloads(response)

    first_text = "".join(
        payload["content"]
        for payload in first_payloads
        if payload["event_type"] == "text"
    )
    second_text = "".join(
        payload["content"]
        for payload in second_payloads
        if payload["event_type"] == "text"
    )
    first_checkpoint = next(
        payload for payload in first_payloads if payload["event_type"] == "checkpoint"
    )
    second_checkpoint = next(
        payload for payload in second_payloads if payload["event_type"] == "checkpoint"
    )

    assert first_text == "turn:1"
    assert second_text == "turn:2"
    assert first_checkpoint["thread_id"] == "resume_1"
    assert second_checkpoint["thread_id"] == "resume_1"
    assert first_checkpoint["checkpoint_id"] != second_checkpoint["checkpoint_id"]
    assert second_checkpoint["message_count"] > first_checkpoint["message_count"]


def test_chat_stream_interrupt_and_resume(monkeypatch):
    from langgraph.errors import GraphInterrupt
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.types import Command
    from services.trace_service import TraceService
    from fastapi.testclient import TestClient
    from main import app
    import json

    client = TestClient(app)

    def _sse_payloads(response):
        payloads = []
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                payloads.append(json.loads(line[6:]))
        return payloads

    class MockSaver:
        async def setup(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "interrupt_1",
                "checkpoint_id": "cp-1",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": ["hello"],
            "route_history": [],
            "streaming_status": "running",
        }
        next = ()
        created_at = "2026-03-11T00:00:00+00:00"

    class InterruptGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "data": {
                    "output": Command(
                        update={
                            "active_team": "research",
                            "active_worker": None,
                            "streaming_status": "running",
                        },
                        goto="research_team",
                    )
                },
            }
            # Instead of triggering langgraph's internal interrupt() logic which requires context,
            # we manually raise a raw GraphInterrupt simulating what the checkpointer would catch.
            raise GraphInterrupt([{"value": "Requires user approval"}])  # type: ignore

        async def aget_state(self, config, subgraphs=False):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type(
            "B", (), {"compile": lambda self, checkpointer: InterruptGraph()}
        )(),
    )

    async def mock_create_events(*args, **kwargs):
        return []

    monkeypatch.setattr(TraceService, "create_events", mock_create_events)

    async def mock_log_message(*args, **kwargs):
        pass

    from services.logging_service import LoggingService

    monkeypatch.setattr(LoggingService, "log_message", mock_log_message)

    with client.stream(
        "POST",
        "/api/chat",
        json={"message": "do something dangerous", "thread_id": "interrupt_1"},
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert any(
        p.get("status") == "interrupted" for p in payloads
    ), f"Expected 'interrupted' status, but got: {payloads}"

    class ResumeGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "data": {
                    "output": Command(
                        update={
                            "active_team": None,
                            "active_worker": None,
                            "streaming_status": "completed",
                        },
                        goto="__end__",
                    )
                },
            }

        async def aget_state(self, config, subgraphs=False):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: ResumeGraph()})(),
    )

    with client.stream(
        "POST",
        "/api/chat/resume",
        json={
            "action": "approve",
            "thread_id": "interrupt_1",
            "feedback": "Looks good",
        },
    ) as response:
        resume_payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert any(p.get("status") == "completed" for p in resume_payloads)
