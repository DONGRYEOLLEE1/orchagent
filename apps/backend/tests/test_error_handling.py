import json
import pytest
from fastapi.testclient import TestClient
from main import app
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

client = TestClient(app)

def test_chat_stream_error_fallback(monkeypatch):
    """Unexpected graph errors should emit normalized errored status + error events."""

    class MockSaver:
        async def setup(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())

    class CrashGraph:
        async def astream_events(self, *args, **kwargs):
            raise RuntimeError("LLM Service Unavailable")
            yield  # To qualify as an async generator

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("B", (), {"compile": lambda self, checkpointer: CrashGraph()})(),
    )

    async def mock_log_message(*args, **kwargs):
        pass
    from services.logging_service import LoggingService
    monkeypatch.setattr(LoggingService, "log_message", mock_log_message)
    from services.trace_service import TraceService

    async def mock_create_events(*args, **kwargs):
        return []

    monkeypatch.setattr(TraceService, "create_events", mock_create_events)

    with client.stream("POST", "/api/chat", json={"message": "fail me", "thread_id": "999"}) as response:
        payloads = [
            json.loads(line[6:])
            for line in response.iter_lines()
            if line and line.startswith("data: ")
        ]

    assert any(
        payload["event_type"] == "status" and payload["status"] == "errored"
        for payload in payloads
    )
    assert any(
        payload["event_type"] == "error"
        and payload["message"] == "LLM Service Unavailable"
        for payload in payloads
    )
