import pytest
from fastapi.testclient import TestClient
from main import app
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

client = TestClient(app)


class MockTuple:
    def __init__(self, tasks=None):
        self.tasks = tasks if tasks is not None else ["dummy_task"]


class MockSaver:
    async def setup(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def aget_tuple(self, config):
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id == "invalid_id":
            return None
        if thread_id == "not_interrupted_id":
            return MockTuple(tasks=[])
        return MockTuple(tasks=["task"])


@pytest.fixture
def mock_postgres_saver(monkeypatch):
    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())


def test_resume_edge_case_3_invalid_thread_id(mock_postgres_saver):
    """
    Edge Case 3: Resume with invalid thread ID.
    Should return 404.
    """
    response = client.post(
        "/api/chat/resume", json={"thread_id": "invalid_id", "action": "approve"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"


def test_resume_edge_case_4_not_interrupted(mock_postgres_saver):
    """
    Edge Case 4: Resume when not interrupted.
    Should return 400.
    """
    response = client.post(
        "/api/chat/resume",
        json={"thread_id": "not_interrupted_id", "action": "approve"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Graph is not in an interrupted state"


def test_resume_edge_case_5_malicious_feedback_length():
    """
    Edge Case 5: Maliciously long feedback payload.
    Should return 422 Unprocessable Entity due to Pydantic validation.
    """
    long_feedback = "a" * 2500  # max_length is 2000
    response = client.post(
        "/api/chat/resume",
        json={"thread_id": "valid_id", "action": "feedback", "feedback": long_feedback},
    )
    assert response.status_code == 422
    error_detail = response.json()["detail"]
    assert any(
        "String should have at most 2000 characters" in str(err) for err in error_detail
    )


def test_resume_edge_case_5_valid_feedback(mock_postgres_saver, monkeypatch):
    """
    Ensure valid feedback payload is accepted.
    """
    # Mock LoggingService to prevent db errors
    from services.logging_service import LoggingService

    async def mock_log(*args, **kwargs):
        pass

    monkeypatch.setattr(LoggingService, "log_message", mock_log)

    valid_feedback = "a" * 1500
    # Use stream context manager because it returns EventSourceResponse (streaming)
    with client.stream(
        "POST",
        "/api/chat/resume",
        json={
            "thread_id": "valid_id",
            "action": "feedback",
            "feedback": valid_feedback,
        },
    ) as response:
        assert response.status_code == 200


def test_resume_allows_paused_checkpoint_without_pending_tasks(monkeypatch):
    class PausedSaver(MockSaver):
        async def aget_tuple(self, config):
            thread_id = config.get("configurable", {}).get("thread_id")
            if thread_id == "paused_checkpoint_id":
                return MockTuple(tasks=[])
            return await super().aget_tuple(config)

    monkeypatch.setattr(
        AsyncPostgresSaver, "from_conn_string", lambda x: PausedSaver()
    )

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "paused_checkpoint_id",
                "checkpoint_id": "cp-paused",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": ["user"],
            "route_history": [],
            "streaming_status": "completed",
        }
        next = ("head_supervisor",)
        created_at = "2026-03-11T00:00:00+00:00"

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

    from services.logging_service import LoggingService
    from services.trace_service import TraceService

    async def mock_log(*args, **kwargs):
        pass

    async def mock_create_events(*args, **kwargs):
        return []

    monkeypatch.setattr(LoggingService, "log_message", mock_log)
    monkeypatch.setattr(TraceService, "create_events", mock_create_events)

    with client.stream(
        "POST",
        "/api/chat/resume",
        json={"thread_id": "paused_checkpoint_id", "action": "approve"},
    ) as response:
        assert response.status_code == 200


@pytest.mark.real_thread_ownership
def test_resume_returns_404_for_thread_owned_by_another_user(monkeypatch):
    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class DummySessionFactory:
        def __call__(self):
            return DummySession()

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        return type("Session", (), {"user_id": "other-user"})()

    monkeypatch.setattr("api.routes.chat.AsyncSessionLocal", DummySessionFactory())
    monkeypatch.setattr(
        "api.routes.chat.ThreadService.get_chat_session",
        mock_get_chat_session,
    )

    response = client.post(
        "/api/chat/resume",
        json={"thread_id": "owned-by-other", "action": "approve"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"
