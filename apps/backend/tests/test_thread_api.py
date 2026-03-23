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
        pinned=False,
        archived=False,
    )

    async def mock_list_thread_summaries(db, *, user_id, limit):
        assert user_id == "test-user"
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
                "pinned": False,
                "archived": False,
            }
        ]
    }


def test_list_threads_returns_empty_list(monkeypatch):
    async def mock_list_thread_summaries(db, *, user_id, limit):
        assert user_id == "test-user"
        assert limit == 50
        return []

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "list_thread_summaries", mock_list_thread_summaries)
    try:
        response = client.get("/api/threads")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {"threads": []}


def test_list_threads_preserves_service_order_and_summary_fields(monkeypatch):
    base_time = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    summaries = [
        ThreadSummary(
            thread_id="thread-new",
            title="newest prompt",
            preview="newest answer",
            created_at=base_time,
                last_activity_at=base_time,
                message_count=4,
                latest_status="completed",
                checkpoint_id="cp-new",
                pinned=False,
                archived=False,
            ),
            ThreadSummary(
                thread_id="thread-old",
            title="older prompt",
            preview="older preview",
            created_at=base_time,
                last_activity_at=base_time,
                message_count=1,
                latest_status="interrupted",
                checkpoint_id="cp-old",
                pinned=False,
                archived=False,
            ),
        ]

    async def mock_list_thread_summaries(db, *, user_id, limit):
        assert user_id == "test-user"
        assert limit == 20
        return summaries

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "list_thread_summaries", mock_list_thread_summaries)
    try:
        response = client.get("/api/threads?limit=20")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert [thread["thread_id"] for thread in body["threads"]] == [
        "thread-new",
        "thread-old",
    ]
    assert body["threads"][0]["message_count"] == 4
    assert body["threads"][1]["latest_status"] == "interrupted"


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
            pinned=False,
            archived=False,
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

    async def mock_get_thread_detail(db, thread_id, *, user_id):
        assert thread_id == "thread-2"
        assert user_id == "test-user"
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


def test_get_thread_returns_user_only_detail(monkeypatch):
    created_at = datetime(2026, 3, 22, 11, 0, 0, tzinfo=timezone.utc)
    message_id = uuid4()
    detail = ThreadDetail(
        thread=ThreadSummary(
            thread_id="thread-user-only",
            title="Single prompt",
            preview="Single prompt",
            created_at=created_at,
            last_activity_at=created_at,
            message_count=1,
            latest_status="running",
            checkpoint_id="cp-user-only",
            pinned=False,
            archived=False,
        ),
        messages=[
            ThreadMessage(
                id=message_id,
                role="user",
                content="only user message",
                created_at=created_at,
            )
        ],
    )

    async def mock_get_thread_detail(db, thread_id, *, user_id):
        assert thread_id == "thread-user-only"
        assert user_id == "test-user"
        return detail

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_thread_detail", mock_get_thread_detail)
    try:
        response = client.get("/api/threads/thread-user-only")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["messages"] == [
        {
            "id": str(message_id),
            "role": "user",
            "content": "only user message",
            "created_at": "2026-03-22T11:00:00Z",
        }
    ]


def test_get_thread_returns_resume_messages_in_existing_order(monkeypatch):
    created_at = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)
    detail = ThreadDetail(
        thread=ThreadSummary(
            thread_id="thread-resume",
            title="Resume thread",
            preview="approved answer",
            created_at=created_at,
            last_activity_at=created_at,
            message_count=4,
            latest_status="completed",
            checkpoint_id="cp-resume",
            pinned=False,
            archived=False,
        ),
        messages=[
            ThreadMessage(
                id=uuid4(),
                role="user",
                content="first request",
                created_at=created_at,
            ),
            ThreadMessage(
                id=uuid4(),
                role="assistant",
                content="needs approval",
                created_at=created_at,
            ),
            ThreadMessage(
                id=uuid4(),
                role="user",
                content="approved",
                created_at=created_at,
            ),
            ThreadMessage(
                id=uuid4(),
                role="assistant",
                content="final answer",
                created_at=created_at,
            ),
        ],
    )

    async def mock_get_thread_detail(db, thread_id, *, user_id):
        assert thread_id == "thread-resume"
        assert user_id == "test-user"
        return detail

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_thread_detail", mock_get_thread_detail)
    try:
        response = client.get("/api/threads/thread-resume")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert [message["content"] for message in response.json()["messages"]] == [
        "first request",
        "needs approval",
        "approved",
        "final answer",
    ]


def test_get_thread_returns_404_for_missing_thread(monkeypatch):
    async def mock_get_thread_detail(db, thread_id, *, user_id):
        assert thread_id == "missing-thread"
        assert user_id == "test-user"
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
