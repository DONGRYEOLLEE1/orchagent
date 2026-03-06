import pytest
from fastapi.testclient import TestClient
from main import app
from services.trace_service import TraceService
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

client = TestClient(app)

def test_health_check():
    """Health check endpoint should return 200 OK."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "OrchAgent backend is running."}

def test_chat_stream_success(monkeypatch):
    """Test SSE streaming using mocks for Checkpointer and Graph execution."""
    
    # 1. Mock AsyncPostgresSaver to bypass DB connection
    class MockSaver:
        async def setup(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())
    
    # 2. Mock the Graph execution (astream_events)
    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            # Stub yielding two mock events
            yield {"event": "on_chain_start", "name": "OrchAgent", "data": {}}
            yield {"event": "on_node_start", "name": "head_supervisor", "data": {}}
            
    # Intercept get_orchagent_graph to return our mock compiler
    monkeypatch.setattr("api.routes.chat.get_orchagent_graph", lambda: type("B", (), {"compile": lambda self, checkpointer: MockGraph()})())
    
    # 3. Mock TraceService to prevent DB write attempts
    async def mock_create_event(*args, **kwargs):
        pass
    monkeypatch.setattr(TraceService, "create_event", mock_create_event)

    # 4. Execute streaming request
    with client.stream("POST", "/api/chat", json={"message": "hello", "thread_id": "test_123"}) as response:
        events = list(response.iter_lines())
        # Filter empty lines and keep only data events
        events = [e for e in events if e and e.startswith("data: ")]
        
        assert len(events) >= 2
        assert 'head_supervisor' in events[1]
