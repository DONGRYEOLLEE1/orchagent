import asyncio
from fastapi.testclient import TestClient
from main import app
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from services.trace_service import TraceService

client = TestClient(app)


def test_chat_stream_client_disconnect_saves_traces(monkeypatch):
    """
    Edge Case 8: 극단적으로 짧은 연결 끊김 (Client Disconnect)
    Test that trace events collected so far are persisted even if the client disconnects (raises CancelledError).
    """

    class MockSaver:
        async def setup(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aget_tuple(self, config):
            return None  # Mock not found or simply empty

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())

    # We mock the graph to yield one event then raise CancelledError
    class DisconnectGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "name": "research_agent",
                "data": {
                    "chunk": type(
                        "Chunk",
                        (),
                        {"content": "First chunk of response", "response_metadata": {}},
                    )()
                },
                "run_id": "mock_run_id",
            }
            # Simulate client disconnect
            raise asyncio.CancelledError()

        async def aget_state(self, config, subgraphs=False):
            return type(
                "Snapshot",
                (),
                {"config": {}, "values": {}, "next": (), "created_at": ""},
            )()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type(
            "B", (), {"compile": lambda self, checkpointer: DisconnectGraph()}
        )(),
    )

    # We need to capture what TraceService.create_events receives
    captured_traces = []

    async def mock_create_events(db, traces):
        captured_traces.extend(traces)
        return []

    monkeypatch.setattr(TraceService, "create_events", mock_create_events)

    # Also mock LoggingService so it doesn't fail on db
    from services.logging_service import LoggingService

    async def mock_log(*args, **kwargs):
        pass

    monkeypatch.setattr(LoggingService, "log_message", mock_log)

    try:
        # We manually iterate to trigger the CancelledError
        response = client.stream(
            "POST",
            "/api/chat",
            json={"message": "hello", "thread_id": "disconnect_thread"},
        )
        with response as r:
            for line in r.iter_lines():
                pass
    except Exception:
        # Depending on how testclient handles CancelledError, it might bubble up or get swallowed
        pass

    # The final assertion: even though the stream was cancelled, the "First chunk" trace
    # and the status trace must have been appended and persisted in the finally block.

    # Internal worker text is no longer emitted on the final-answer channel,
    # so disconnect persistence should still keep the running status trace
    # without fabricating a user-facing text summary.
    status_traces = [
        t for t in captured_traces if t.payload.get("event_type") == "status"
    ]
    summary_traces = [
        t for t in captured_traces if t.payload.get("event_type") == "text_summary"
    ]

    assert any(trace.payload.get("status") == "running" for trace in status_traces)
    assert summary_traces == []
