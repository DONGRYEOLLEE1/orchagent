import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from main import app
client = TestClient(app)


def _sse_payloads(response):
    payloads = []
    for line in response.iter_lines():
        if line and line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    return payloads


class MockChunk:
    def __init__(self, content):
        self.content = content
        self.additional_kwargs = {}


def _mock_saver():
    class MockSaver:
        async def setup(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def aget_tuple(self, config):
            state = SimpleNamespace()
            state.tasks = ["dummy"]
            return state

    return MockSaver()


def test_chat_stream_records_completed_turn_lifecycle(monkeypatch):
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda _: _mock_saver())

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "thread-completed",
                "checkpoint_id": "cp-completed",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": [],
            "route_history": [],
            "streaming_status": "completed",
            "response_mode": "finalizer",
        }
        next = ()
        created_at = "2026-03-24T00:00:00+00:00"

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "metadata": {"langgraph_node": "finalizer"},
                "data": {"chunk": MockChunk('{"content":"done"}')},
                "run_id": "finalizer-run",
            }
            yield {
                "event": "on_chain_end",
                "name": "finalizer",
                "data": {
                    "output": Command(
                        update={"streaming_status": "completed"},
                    )
                },
            }

        async def aget_state(self, config, subgraphs=True):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: MockGraph()})(),
    )
    async def mock_persist_traces(*args, **kwargs):
        return None

    logged_messages = []

    async def mock_log_message(*args, **kwargs):
        message = SimpleNamespace(id=uuid4(), role=kwargs.get("role"))
        logged_messages.append(message)
        return message

    start_turn_calls = []
    first_token_calls = []
    finalize_calls = []

    async def mock_start_turn(*args, **kwargs):
        turn = SimpleNamespace(id=uuid4(), trace_id="trace-completed")
        start_turn_calls.append(turn)
        return turn

    async def mock_mark_first_token(turn_id, first_token_at):
        first_token_calls.append((turn_id, first_token_at))

    async def mock_finalize_turn(params):
        finalize_calls.append(params)

    monkeypatch.setattr("services.logging_service.LoggingService.log_message_with_fresh_session", mock_log_message)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.start_turn_with_fresh_session", mock_start_turn)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.mark_first_token_with_fresh_session", mock_mark_first_token)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.finalize_turn_with_fresh_session", mock_finalize_turn)
    monkeypatch.setattr("services.trace_service.TraceService.persist_events_with_fresh_session", mock_persist_traces)

    with client.stream(
        "POST", "/api/chat", json={"message": "hello", "thread_id": "thread-completed"}
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert any(payload["event_type"] == "text" for payload in payloads)
    assert len(start_turn_calls) == 1
    assert len(first_token_calls) == 1
    assert finalize_calls[-1].status == "completed"
    assert finalize_calls[-1].response_message_id == logged_messages[-1].id


def test_chat_stream_records_interrupted_turn_lifecycle(monkeypatch):
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda _: _mock_saver())

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "thread-interrupted",
                "checkpoint_id": "cp-interrupted",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": [],
            "route_history": [],
            "streaming_status": "running",
            "response_mode": "finalizer",
        }
        next = ("human_approval",)
        created_at = "2026-03-24T00:00:00+00:00"

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            if False:
                yield None

        async def aget_state(self, config, subgraphs=True):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: MockGraph()})(),
    )
    async def mock_persist_traces(*args, **kwargs):
        return None

    async def mock_log_message(*args, **kwargs):
        return SimpleNamespace(id=uuid4(), role=kwargs.get("role"))

    async def mock_start_turn(*args, **kwargs):
        return SimpleNamespace(id=uuid4(), trace_id="trace-interrupted")

    finalize_calls = []

    async def mock_finalize_turn(params):
        finalize_calls.append(params)

    monkeypatch.setattr("services.logging_service.LoggingService.log_message_with_fresh_session", mock_log_message)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.start_turn_with_fresh_session", mock_start_turn)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.finalize_turn_with_fresh_session", mock_finalize_turn)
    monkeypatch.setattr("services.trace_service.TraceService.persist_events_with_fresh_session", mock_persist_traces)

    with client.stream(
        "POST", "/api/chat", json={"message": "need approval", "thread_id": "thread-interrupted"}
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert any(
        payload["event_type"] == "status" and payload["status"] == "interrupted"
        for payload in payloads
    )
    assert finalize_calls[-1].status == "interrupted"


def test_chat_stream_records_errored_turn_lifecycle(monkeypatch):
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda _: _mock_saver())

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        async def aget_state(self, config, subgraphs=True):
            raise AssertionError("aget_state should not be called")

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: MockGraph()})(),
    )
    async def mock_persist_traces(*args, **kwargs):
        return None

    async def mock_log_message(*args, **kwargs):
        return SimpleNamespace(id=uuid4(), role=kwargs.get("role"))

    async def mock_start_turn(*args, **kwargs):
        return SimpleNamespace(id=uuid4(), trace_id="trace-errored")

    finalize_calls = []

    async def mock_finalize_turn(params):
        finalize_calls.append(params)

    monkeypatch.setattr("services.logging_service.LoggingService.log_message_with_fresh_session", mock_log_message)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.start_turn_with_fresh_session", mock_start_turn)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.finalize_turn_with_fresh_session", mock_finalize_turn)
    monkeypatch.setattr("services.trace_service.TraceService.persist_events_with_fresh_session", mock_persist_traces)

    with client.stream(
        "POST", "/api/chat", json={"message": "explode", "thread_id": "thread-errored"}
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert any(
        payload["event_type"] == "status" and payload["status"] == "errored"
        for payload in payloads
    )
    assert finalize_calls[-1].status == "errored"


def test_chat_resume_records_resume_turn_kind(monkeypatch):
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda _: _mock_saver())

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "thread-resume",
                "checkpoint_id": "cp-resume",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": [],
            "route_history": [],
            "streaming_status": "completed",
            "response_mode": "finalizer",
        }
        next = ()
        created_at = "2026-03-24T00:00:00+00:00"

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "metadata": {"langgraph_node": "finalizer"},
                "data": {"chunk": MockChunk('{"content":"resume done"}')},
                "run_id": "resume-run",
            }
            yield {
                "event": "on_chain_end",
                "name": "finalizer",
                "data": {"output": Command(update={"streaming_status": "completed"})},
            }

        async def aget_state(self, config, subgraphs=True):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: MockGraph()})(),
    )

    async def mock_log_message(*args, **kwargs):
        return SimpleNamespace(id=uuid4(), role=kwargs.get("role"))

    start_turn_kwargs = []
    finalize_calls = []

    async def mock_start_turn(**kwargs):
        start_turn_kwargs.append(kwargs)
        return SimpleNamespace(id=uuid4(), trace_id="trace-resume")

    async def mock_finalize_turn(params):
        finalize_calls.append(params)

    async def mock_persist_traces(*args, **kwargs):
        return None

    monkeypatch.setattr("services.logging_service.LoggingService.log_message_with_fresh_session", mock_log_message)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.start_turn_with_fresh_session", mock_start_turn)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.finalize_turn_with_fresh_session", mock_finalize_turn)
    monkeypatch.setattr("services.trace_service.TraceService.persist_events_with_fresh_session", mock_persist_traces)

    with client.stream(
        "POST",
        "/api/chat/resume",
        json={"thread_id": "thread-resume", "action": "approve", "feedback": "ok"},
    ) as response:
        _sse_payloads(response)

    assert response.status_code == 200
    assert start_turn_kwargs[0]["request_kind"] == "resume"
    assert finalize_calls[-1].status == "completed"
