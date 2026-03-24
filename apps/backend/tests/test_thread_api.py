from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from core.database import get_db
from main import app
from services.thread_service import ThreadDetail, ThreadMessage, ThreadSummary

client = TestClient(app)


async def _override_get_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    yield db


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


def test_list_threads_returns_pinned_threads_first(monkeypatch):
    base_time = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    summaries = [
        ThreadSummary(
            thread_id="thread-pinned",
            title="Pinned thread",
            preview="older preview",
            created_at=base_time,
            last_activity_at=base_time,
            message_count=1,
            latest_status="completed",
            checkpoint_id="cp-pinned",
            pinned=True,
            archived=False,
        ),
        ThreadSummary(
            thread_id="thread-unpinned",
            title="Unpinned thread",
            preview="newer preview",
            created_at=base_time,
            last_activity_at=base_time.replace(hour=11),
            message_count=2,
            latest_status="completed",
            checkpoint_id="cp-unpinned",
            pinned=False,
            archived=False,
        ),
    ]

    async def mock_list_thread_summaries(db, *, user_id, limit):
        assert user_id == "test-user"
        return summaries

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "list_thread_summaries", mock_list_thread_summaries)
    try:
        response = client.get("/api/threads")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert [thread["thread_id"] for thread in body["threads"]] == [
        "thread-pinned",
        "thread-unpinned",
    ]


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


def test_delete_thread_returns_204(monkeypatch):
    async def mock_delete_thread(db, thread_id, *, user_id):
        assert thread_id == "thread-delete"
        assert user_id == "test-user"
        return True

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "delete_thread", mock_delete_thread)
    try:
        response = client.delete("/api/threads/thread-delete")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 204
    assert response.text == ""


def test_delete_thread_returns_404_for_missing_thread(monkeypatch):
    async def mock_delete_thread(db, thread_id, *, user_id):
        assert thread_id == "thread-missing"
        assert user_id == "test-user"
        return False

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "delete_thread", mock_delete_thread)
    try:
        response = client.delete("/api/threads/thread-missing")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Thread not found"}


def test_generate_ai_thread_title_creates_title_for_first_message(monkeypatch):
    created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    summary = ThreadSummary(
        thread_id="thread-ai-1",
        title="RoPE 논문 탐색",
        preview="Latest reply",
        created_at=created_at,
        last_activity_at=created_at,
        message_count=1,
        latest_status="running",
        checkpoint_id=None,
        pinned=False,
        archived=False,
    )

    from services.logging_service import LoggingService
    from services.thread_profile_service import ThreadProfileService
    from services.thread_service import ThreadService
    from services.thread_title_service import ThreadTitleService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        assert thread_id == "thread-ai-1"
        assert user_id is None
        return None

    async def mock_get_or_create_session(db, thread_id, user_id=None):
        assert thread_id == "thread-ai-1"
        assert user_id == "test-user"
        return object()

    async def mock_get_thread_profile(db, thread_id, user_id):
        return None

    async def mock_get_counts(db, thread_id):
        assert thread_id == "thread-ai-1"
        return {"user": 1, "assistant": 0}

    async def mock_generate_title(message):
        assert "RoPE 논문" in message
        return "RoPE 논문 탐색"

    async def mock_set_generated_title_if_missing(*args, **kwargs):
        assert kwargs["thread_id"] == "thread-ai-1"
        assert kwargs["user_id"] == "test-user"
        assert kwargs["title"] == "RoPE 논문 탐색"
        return object()

    async def mock_get_thread_summary(db, thread_id, *, user_id):
        assert thread_id == "thread-ai-1"
        assert user_id == "test-user"
        return summary

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(LoggingService, "get_or_create_session", mock_get_or_create_session)
    monkeypatch.setattr(ThreadProfileService, "get_thread_profile", mock_get_thread_profile)
    monkeypatch.setattr(ThreadService, "get_thread_message_role_counts", mock_get_counts)
    monkeypatch.setattr(ThreadTitleService, "generate_title", mock_generate_title)
    monkeypatch.setattr(
        ThreadProfileService,
        "set_generated_title_if_missing",
        mock_set_generated_title_if_missing,
    )
    monkeypatch.setattr(ThreadService, "get_thread_summary", mock_get_thread_summary)
    try:
        response = client.post(
            "/api/threads/thread-ai-1/ai-title",
            json={"message": "웹검색을 통해 RoPE 논문을 탐색하고 메인 연구자가 원하는 바는 무엇인지 설명해주세요."},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["title"] == "RoPE 논문 탐색"


def test_generate_ai_thread_title_skips_when_manual_title_exists(monkeypatch):
    created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    summary = ThreadSummary(
        thread_id="thread-ai-2",
        title="수동 제목",
        preview="Latest reply",
        created_at=created_at,
        last_activity_at=created_at,
        message_count=1,
        latest_status="running",
        checkpoint_id=None,
        pinned=False,
        archived=False,
    )

    from services.thread_profile_service import ThreadProfileService
    from services.thread_service import ThreadService
    from services.thread_title_service import ThreadTitleService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        return type("Session", (), {"user_id": "test-user"})()

    async def mock_get_thread_profile(db, thread_id, user_id):
        return type("Profile", (), {"title_override": "수동 제목"})()

    async def mock_get_thread_summary(db, thread_id, *, user_id):
        return summary

    async def fail_generate_title(message):
        raise AssertionError("generate_title should not be called when manual title exists")

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(ThreadProfileService, "get_thread_profile", mock_get_thread_profile)
    monkeypatch.setattr(ThreadService, "get_thread_summary", mock_get_thread_summary)
    monkeypatch.setattr(ThreadTitleService, "generate_title", fail_generate_title)
    try:
        response = client.post(
            "/api/threads/thread-ai-2/ai-title",
            json={"message": "웹검색으로 JWT를 설명해줘"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["title"] == "수동 제목"


def test_generate_ai_thread_title_skips_existing_threads_after_first_user_turn(monkeypatch):
    created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    summary = ThreadSummary(
        thread_id="thread-ai-3",
        title="기존 제목",
        preview="Latest reply",
        created_at=created_at,
        last_activity_at=created_at,
        message_count=3,
        latest_status="completed",
        checkpoint_id="cp-1",
        pinned=False,
        archived=False,
    )

    from services.thread_profile_service import ThreadProfileService
    from services.thread_service import ThreadService
    from services.thread_title_service import ThreadTitleService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        return type("Session", (), {"user_id": "test-user"})()

    async def mock_get_thread_profile(db, thread_id, user_id):
        return None

    async def mock_get_counts(db, thread_id):
        return {"user": 2, "assistant": 1}

    async def mock_get_thread_summary(db, thread_id, *, user_id):
        return summary

    async def fail_generate_title(message):
        raise AssertionError("generate_title should not be called for existing follow-up turns")

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(ThreadProfileService, "get_thread_profile", mock_get_thread_profile)
    monkeypatch.setattr(ThreadService, "get_thread_message_role_counts", mock_get_counts)
    monkeypatch.setattr(ThreadService, "get_thread_summary", mock_get_thread_summary)
    monkeypatch.setattr(ThreadTitleService, "generate_title", fail_generate_title)
    try:
        response = client.post(
            "/api/threads/thread-ai-3/ai-title",
            json={"message": "추가 질문입니다"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["title"] == "기존 제목"


def test_get_thread_telemetry_returns_reasoning_and_suggestions(monkeypatch):
    from services.thread_service import ThreadService
    from services.thread_telemetry_service import ThreadTelemetry, ThreadTelemetryService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        assert thread_id == "thread-telemetry-1"
        assert user_id == "test-user"
        return type("Session", (), {"user_id": "test-user"})()

    async def mock_get_thread_telemetry(db, thread_id):
        assert thread_id == "thread-telemetry-1"
        return ThreadTelemetry(
            reasoning_summary="저장된 reasoning",
            suggested_queries=["후속 질문 1", "후속 질문 2"],
        )

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(
        ThreadTelemetryService,
        "get_thread_telemetry",
        mock_get_thread_telemetry,
    )
    try:
        response = client.get("/api/threads/thread-telemetry-1/telemetry")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread-telemetry-1",
        "reasoning_summary": "저장된 reasoning",
        "suggested_queries": ["후속 질문 1", "후속 질문 2"],
    }


def test_generate_suggested_queries_persists_summary_and_returns_telemetry(monkeypatch):
    from services.thread_service import ThreadService, ThreadSuggestionContext
    from services.thread_suggested_query_service import ThreadSuggestedQueryService
    from services.thread_telemetry_service import ThreadTelemetry, ThreadTelemetryService
    from services.trace_service import TraceService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        assert thread_id == "thread-suggest-1"
        assert user_id == "test-user"
        return type("Session", (), {"user_id": "test-user"})()

    async def mock_get_latest_suggestion_context(db, thread_id):
        assert thread_id == "thread-suggest-1"
        return ThreadSuggestionContext(
            user_content="RoPE 논문 설명해줘",
            assistant_content="RoPE 논문에 대한 최종 답변",
        )

    async def mock_generate_suggestions(*, user_message, assistant_message):
        assert "RoPE" in user_message
        assert "최종 답변" in assistant_message
        return ["RoPE와 ALiBi 차이도 비교해줘", "대표 후속 연구 흐름도 정리해줘"]

    async def mock_create_event(db, *, thread_id, event_type, node_name, payload):
        assert thread_id == "thread-suggest-1"
        assert event_type == "suggested_queries_summary"
        assert node_name == "assistant"
        assert payload["suggested_queries"] == [
            "RoPE와 ALiBi 차이도 비교해줘",
            "대표 후속 연구 흐름도 정리해줘",
        ]
        return object()

    async def mock_get_thread_telemetry(db, thread_id):
        assert thread_id == "thread-suggest-1"
        return ThreadTelemetry(
            reasoning_summary="reasoning summary",
            suggested_queries=[
                "RoPE와 ALiBi 차이도 비교해줘",
                "대표 후속 연구 흐름도 정리해줘",
            ],
        )

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(
        ThreadService,
        "get_latest_suggestion_context",
        mock_get_latest_suggestion_context,
    )
    monkeypatch.setattr(
        ThreadSuggestedQueryService,
        "generate_suggestions",
        mock_generate_suggestions,
    )
    monkeypatch.setattr(TraceService, "create_event", mock_create_event)
    monkeypatch.setattr(
        ThreadTelemetryService,
        "get_thread_telemetry",
        mock_get_thread_telemetry,
    )
    try:
        response = client.post("/api/threads/thread-suggest-1/suggested-queries")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["suggested_queries"] == [
        "RoPE와 ALiBi 차이도 비교해줘",
        "대표 후속 연구 흐름도 정리해줘",
    ]
