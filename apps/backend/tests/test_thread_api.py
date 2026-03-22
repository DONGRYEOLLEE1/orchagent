from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from core.database import get_db
from main import app
from services.thread_service import ThreadDetail, ThreadMessage, ThreadSummary

client = TestClient(app)


async def _override_get_db():
    yield object()


def test_list_threads_returns_thread_summaries(monkeypatch):
    created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    summary = ThreadSummary(
        thread_id="thread-1",
        title="First prompt",
        preview="Latest reply",
        created_at=created_at,
        last_activity_at=created_at,
        message_count=2,
        latest_status="completed",
        checkpoint_id="cp-1",
    )

    async def mock_list_thread_summaries(db, *, limit):
        assert limit == 10
        return [summary]

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "list_thread_summaries", mock_list_thread_summaries)
    try:
        response = client.get("/api/threads?limit=10")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {
        "threads": [
            {
                "thread_id": "thread-1",
                "title": "First prompt",
                "preview": "Latest reply",
                "created_at": "2026-03-22T10:00:00Z",
                "last_activity_at": "2026-03-22T10:00:00Z",
                "message_count": 2,
                "latest_status": "completed",
                "checkpoint_id": "cp-1",
            }
        ]
    }


def test_get_thread_returns_detail(monkeypatch):
    created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    message_id = uuid4()
    detail = ThreadDetail(
        thread=ThreadSummary(
            thread_id="thread-2",
            title="Conversation title",
            preview="Assistant preview",
            created_at=created_at,
            last_activity_at=created_at,
            message_count=2,
            latest_status="interrupted",
            checkpoint_id="cp-2",
        ),
        messages=[
            ThreadMessage(
                id=message_id,
                role="user",
                content="hello",
                created_at=created_at,
            ),
            ThreadMessage(
                id=uuid4(),
                role="assistant",
                content="hi there",
                created_at=created_at,
            ),
        ],
    )

    async def mock_get_thread_detail(db, thread_id):
        assert thread_id == "thread-2"
        return detail

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_thread_detail", mock_get_thread_detail)
    try:
        response = client.get("/api/threads/thread-2")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["thread"]["thread_id"] == "thread-2"
    assert body["thread"]["latest_status"] == "interrupted"
    assert body["messages"][0] == {
        "id": str(message_id),
        "role": "user",
        "content": "hello",
        "created_at": "2026-03-22T10:00:00Z",
    }
    assert body["messages"][1]["role"] == "assistant"


def test_get_thread_returns_404_for_missing_thread(monkeypatch):
    async def mock_get_thread_detail(db, thread_id):
        assert thread_id == "missing-thread"
        return None

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_thread_detail", mock_get_thread_detail)
    try:
        response = client.get("/api/threads/missing-thread")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Thread not found"}
