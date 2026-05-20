import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from api.routes.chat import _build_usage_write_params
from main import app

client = TestClient(app)


def _sse_payloads(response):
    payloads = []
    for line in response.iter_lines():
        if line and line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    return payloads


class MockOutput:
    def __init__(self):
        self.usage_metadata = {
            "input_tokens": 14,
            "output_tokens": 1523,
            "total_tokens": 1537,
            "input_token_details": {"cache_read": 2, "cache_write": 1},
            "output_token_details": {"reasoning": 1230},
        }
        self.response_metadata = {"model_name": "gpt-5.4-mini"}


def test_build_usage_write_params_extracts_breakdowns():
    event = {
        "run_id": "run-1",
        "metadata": {"langgraph_node": "finalizer"},
        "data": {"output": MockOutput()},
    }

    params = _build_usage_write_params(
        event=event,
        user_id="user-1",
        thread_id="thread-1",
        turn_id=uuid4(),
        trace_id="trace-1",
    )

    assert params is not None
    assert params.input_tokens == 14
    assert params.output_tokens == 1523
    assert params.cache_read_input_tokens == 2
    assert params.cache_write_input_tokens == 1
    assert params.reasoning_output_tokens == 1230
    assert params.text_output_tokens == 293
    assert params.model == "gpt-5.4-mini"


def test_chat_stream_persists_usage_from_model_end(monkeypatch):
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

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda _: MockSaver())

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "usage-thread",
                "checkpoint_id": "cp-usage",
                "checkpoint_ns": "",
            }
        }
        values = {"messages": [], "route_history": [], "streaming_status": "completed"}
        next = ()
        created_at = "2026-03-24T00:00:00+00:00"

    class MockChunk:
        def __init__(self, content):
            self.content = content
            self.additional_kwargs = {}

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "metadata": {"langgraph_node": "finalizer"},
                "data": {"chunk": MockChunk('{"content":"done"}')},
                "run_id": "usage-run",
            }
            yield {
                "event": "on_chat_model_end",
                "name": "ChatOpenAI",
                "metadata": {"langgraph_node": "finalizer"},
                "data": {"output": MockOutput()},
                "run_id": "usage-run",
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

    async def mock_start_turn(**kwargs):
        return SimpleNamespace(id=uuid4(), trace_id="trace-usage")

    usage_calls = []

    async def mock_create_usage_event(params):
        usage_calls.append(params)

    async def mock_persist_traces(*args, **kwargs):
        return None

    async def mock_finalize_turn(params):
        return None

    monkeypatch.setattr("services.logging_service.LoggingService.log_message_with_fresh_session", mock_log_message)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.start_turn_with_fresh_session", mock_start_turn)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.create_usage_event_with_fresh_session", mock_create_usage_event)
    monkeypatch.setattr("services.trace_service.TraceService.persist_events_with_fresh_session", mock_persist_traces)
    monkeypatch.setattr("services.chat_analytics_service.ChatAnalyticsService.finalize_turn_with_fresh_session", mock_finalize_turn)

    with client.stream(
        "POST", "/api/chat", json={"message": "usage", "thread_id": "usage-thread"}
    ) as response:
        _sse_payloads(response)

    assert response.status_code == 200
    assert len(usage_calls) == 1
    assert usage_calls[0].reasoning_output_tokens == 1230
    assert usage_calls[0].cache_read_input_tokens == 2
