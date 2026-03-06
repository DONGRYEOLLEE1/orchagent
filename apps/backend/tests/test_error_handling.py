import pytest
from fastapi.testclient import TestClient
from main import app
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

client = TestClient(app)

def test_chat_stream_error_fallback(monkeypatch):
    """Test that unexpected exceptions during graph execution are gracefully streamed back as error events."""
    
    # 1. Mock DB Checkpointer
    class MockSaver:
        async def setup(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())
    
    # 2. Mock Graph to INTENTIONALLY CRASH
    class CrashGraph:
        async def astream_events(self, *args, **kwargs):
            raise RuntimeError("LLM Service Unavailable")
            yield  # To qualify as an async generator
            
    monkeypatch.setattr("api.routes.chat.get_orchagent_graph", lambda: type("B", (), {"compile": lambda self, checkpointer: CrashGraph()})())
    
    # 3. Execute request and expect error event payload
    with client.stream("POST", "/api/chat", json={"message": "fail me", "thread_id": "999"}) as response:
        events = list(response.iter_lines())
        
        # At least one event should contain the specific error message
        assert any("LLM Service Unavailable" in str(event) for event in events)
