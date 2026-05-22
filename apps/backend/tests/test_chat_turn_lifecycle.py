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
            return SimpleNamespace(tasks=["dummy"])

    return MockSaver()


def _build_snapshot(thread_id: str, *, next_tasks=(), streaming_status="completed"):
    class Snapshot:
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": f"cp-{thread_id}",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": [],
            "route_history": [],
            "streaming_status": streaming_status,
            "response_mode": "finalizer",
        }
        next = next_tasks
        created_at = "2026-03-24T00:00:00+00:00"

    return Snapshot()


def _install_lifecycle_mocks(
    monkeypatch,
    *,
    graph,
    finalize_calls,
    logged_messages=None,
    start_turn_calls=None,
    first_token_calls=None,
    start_turn_kwargs=None,
):
    """Patch in every fresh-session lifecycle hook used by /api/chat and /api/chat/resume."""
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda _: _mock_saver())
    monkeypatch.setattr(
        "services.orchestration_service.OrchestrationService.get_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: graph})(),
    )

    async def mock_log_message(*args, **kwargs):
        message = SimpleNamespace(id=uuid4(), role=kwargs.get("role"))
        if logged_messages is not None:
            logged_messages.append(message)
        return message

    async def mock_start_turn(*args, **kwargs):
        turn = SimpleNamespace(id=uuid4(), trace_id="trace")
        if start_turn_calls is not None:
            start_turn_calls.append(turn)
        if start_turn_kwargs is not None:
            start_turn_kwargs.append(kwargs)
        return turn

    async def mock_mark_first_token(turn_id, first_token_at):
        if first_token_calls is not None:
            first_token_calls.append((turn_id, first_token_at))

    async def mock_finalize_turn(params):
        finalize_calls.append(params)

    async def mock_persist_traces(*args, **kwargs):
        return None

    monkeypatch.setattr("services.logging_service.LoggingService.log_message_with_fresh_session", mock_log_message)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.start_turn_with_fresh_session", mock_start_turn)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.mark_first_token_with_fresh_session", mock_mark_first_token)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.finalize_turn_with_fresh_session", mock_finalize_turn)
    monkeypatch.setattr("services.trace_service.TraceService.persist_events_with_fresh_session", mock_persist_traces)


def test_chat_stream_records_completed_turn_lifecycle(monkeypatch):
    """Successful turn must record start_turn, first_token, and a completed finalize."""
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
                "data": {"output": Command(update={"streaming_status": "completed"})},
            }

        async def aget_state(self, config, subgraphs=True):
            return _build_snapshot("thread-completed")

    logged_messages = []
    start_turn_calls = []
    first_token_calls = []
    finalize_calls = []

    _install_lifecycle_mocks(
        monkeypatch,
        graph=MockGraph(),
        finalize_calls=finalize_calls,
        logged_messages=logged_messages,
        start_turn_calls=start_turn_calls,
        first_token_calls=first_token_calls,
    )

    with client.stream(
        "POST", "/api/chat", json={"message": "hello", "thread_id": "thread-completed"}
    ) as response:
        _sse_payloads(response)

    assert response.status_code == 200
    assert len(start_turn_calls) == 1
    assert len(first_token_calls) == 1
    assert finalize_calls[-1].status == "completed"
    assert finalize_calls[-1].response_message_id == logged_messages[-1].id


def test_chat_stream_records_interrupted_turn_lifecycle(monkeypatch):
    """Paused checkpoint must produce an interrupted finalize and SSE status."""
    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            if False:
                yield None

        async def aget_state(self, config, subgraphs=True):
            return _build_snapshot(
                "thread-interrupted",
                next_tasks=("human_approval",),
                streaming_status="running",
            )

    finalize_calls = []
    _install_lifecycle_mocks(monkeypatch, graph=MockGraph(), finalize_calls=finalize_calls)

    with client.stream(
        "POST", "/api/chat", json={"message": "need approval", "thread_id": "thread-interrupted"}
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert any(
        p["event_type"] == "status" and p["status"] == "interrupted" for p in payloads
    )
    assert finalize_calls[-1].status == "interrupted"


def test_chat_stream_records_errored_turn_lifecycle(monkeypatch):
    """Raised exception inside astream_events must map to an errored finalize."""
    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        async def aget_state(self, config, subgraphs=True):
            raise AssertionError("aget_state should not be called")

    finalize_calls = []
    _install_lifecycle_mocks(monkeypatch, graph=MockGraph(), finalize_calls=finalize_calls)

    with client.stream(
        "POST", "/api/chat", json={"message": "explode", "thread_id": "thread-errored"}
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert any(
        p["event_type"] == "status" and p["status"] == "errored" for p in payloads
    )
    assert finalize_calls[-1].status == "errored"


def test_chat_resume_records_resume_turn_kind(monkeypatch):
    """/api/chat/resume must tag the turn as request_kind=resume."""
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
            return _build_snapshot("thread-resume")

    start_turn_kwargs = []
    finalize_calls = []
    _install_lifecycle_mocks(
        monkeypatch,
        graph=MockGraph(),
        finalize_calls=finalize_calls,
        start_turn_kwargs=start_turn_kwargs,
    )

    with client.stream(
        "POST",
        "/api/chat/resume",
        json={"thread_id": "thread-resume", "action": "approve", "feedback": "ok"},
    ) as response:
        _sse_payloads(response)

    assert response.status_code == 200
    assert start_turn_kwargs[0]["request_kind"] == "resume"
    assert finalize_calls[-1].status == "completed"
