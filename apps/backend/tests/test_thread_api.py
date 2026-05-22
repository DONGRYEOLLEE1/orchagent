from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from fastapi.testclient import TestClient

from core.database import get_db
from main import app
from services.thread_service import ThreadDetail, ThreadMessage, ThreadSummary

client = TestClient(app)


async def _override_get_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    # Without an explicit execute return_value, AsyncMock's auto-generated child
    # mocks surface `.scalar_one_or_none()` as another coroutine, which leaks into
    # `RepositoryBindingService.get_active_binding` and trips `to_response` with
    # "coroutine has no attribute 'id'". Seed an empty SELECT result so routes that
    # probe for bindings / coding summaries cleanly resolve to None.
    empty_result = MagicMock()
    empty_result.scalar_one_or_none = MagicMock(return_value=None)
    empty_result.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    db.execute = AsyncMock(return_value=empty_result)
    yield db


def test_list_threads_returns_summaries_and_respects_service_order(monkeypatch):
    """Threads route flattens ThreadSummary objects into the JSON response."""
    base = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    summaries = [
        ThreadSummary(
            thread_id="thread-pinned",
            title="Pinned thread",
            preview="older preview",
            created_at=base,
            last_activity_at=base,
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
            created_at=base,
            last_activity_at=base.replace(hour=11),
            message_count=2,
            latest_status="completed",
            checkpoint_id="cp-unpinned",
            pinned=False,
            archived=False,
        ),
    ]

    async def mock_list_thread_summaries(db, *, user_id, limit):
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
    # Service-side ordering must be preserved on the wire.
    assert [thread["thread_id"] for thread in body["threads"]] == [
        "thread-pinned",
        "thread-unpinned",
    ]
    assert body["threads"][0]["pinned"] is True


def test_get_thread_absolutizes_message_attachment_urls(monkeypatch):
    """ThreadDetail attachments must come out with absolute http URLs."""
    created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    message_id = uuid4()
    detail = ThreadDetail(
        thread=ThreadSummary(
            thread_id="thread-attachment",
            title="Attachment thread",
            preview="Image prompt",
            created_at=created_at,
            last_activity_at=created_at,
            message_count=1,
            latest_status="completed",
            checkpoint_id="cp-attachment",
            pinned=False,
            archived=False,
        ),
        messages=[
            ThreadMessage(
                id=message_id,
                role="user",
                content="Describe the image",
                created_at=created_at,
                attachments=[
                    {
                        "kind": "image",
                        "url": f"/api/threads/thread-attachment/messages/{message_id}/attachments/0",
                        "alt": "첨부 이미지 1",
                    }
                ],
            )
        ],
    )

    async def mock_get_thread_detail(db, thread_id, *, user_id):
        return detail

    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_thread_detail", mock_get_thread_detail)
    try:
        response = client.get("/api/threads/thread-attachment")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    attachment = response.json()["messages"][0]["attachments"][0]
    assert attachment["url"].startswith("http://testserver/api/threads/thread-attachment/")


def test_get_thread_returns_404_for_missing_thread(monkeypatch):
    async def mock_get_thread_detail(db, thread_id, *, user_id):
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


def test_upload_files_rejects_unsupported_type():
    """Upload route must guard against arbitrary binary uploads."""
    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.post(
            "/api/uploads",
            files=[("files", ("malware.exe", b"noop", "application/octet-stream"))],
            data={"thread_id": "thread-upload"},
            headers={"X-CSRF-Token": "csrf-token"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type"


def test_upload_files_returns_partial_success(monkeypatch):
    """Per-file failures must surface as ``errors`` while accepted files still process."""
    upload_id = uuid4()
    created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)

    async def mock_create_upload_from_prepared(db, *, user_id, prepared, thread_id, storage_path=None):
        return SimpleNamespace(
            id=upload_id,
            input_index=prepared.input_index,
            kind=prepared.kind,
            source_type="device",
            processing_status="ready",
            preview_status="pending",
            file_name=prepared.file_name,
            declared_extension=prepared.declared_extension,
            mime_type=prepared.mime_type,
            sniffed_mime_type=prepared.sniffed_mime_type,
            size_bytes=prepared.size_bytes,
            created_at=created_at,
        )

    from services.upload_service import UploadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(UploadService, "create_upload_from_prepared", mock_create_upload_from_prepared)
    monkeypatch.setattr("api.routes.uploads.settings.ATTACHMENT_MAX_CSV_BYTES", 4)
    try:
        response = client.post(
            "/api/uploads",
            files=[
                ("files", ("keep.json", b'{"ok":1}', "application/json")),
                ("files", ("reject.csv", b"a,b\n1,2\n", "text/csv")),
            ],
            data={"thread_id": "thread-upload"},
            headers={"X-CSRF-Token": "csrf-token"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        monkeypatch.setattr("api.routes.uploads.settings.ATTACHMENT_MAX_CSV_BYTES", 10 * 1024 * 1024)

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["errors"][0]["error_code"] == "file_too_large"


def test_delete_thread_returns_204_or_404(monkeypatch):
    """Successful deletion yields 204; missing thread yields 404."""
    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async def mock_delete_thread_ok(db, thread_id, *, user_id):
            return True

        monkeypatch.setattr(ThreadService, "delete_thread", mock_delete_thread_ok)
        response_ok = client.delete("/api/threads/thread-delete")
        assert response_ok.status_code == 204

        async def mock_delete_thread_missing(db, thread_id, *, user_id):
            return False

        monkeypatch.setattr(ThreadService, "delete_thread", mock_delete_thread_missing)
        response_missing = client.delete("/api/threads/thread-missing")
        assert response_missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_generate_ai_thread_title_creates_title_for_first_message(monkeypatch):
    """First user turn triggers AI title generation and persists via upsert."""
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
    from services.thread_service import ThreadService, ThreadTitlePolicyStats
    from services.thread_title_service import ThreadTitleService
    from services.trace_service import TraceService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        return None

    async def mock_get_or_create_session(db, thread_id, user_id=None):
        return object()

    async def mock_get_thread_profile(db, thread_id, user_id):
        return None

    async def mock_get_title_policy_stats(db, thread_id):
        return ThreadTitlePolicyStats(
            user_turn_count=1,
            assistant_turn_count=0,
            ai_title_generation_count=0,
            has_manual_title_event=False,
        )

    async def mock_generate_title(message):
        return "RoPE 논문 탐색"

    async def mock_upsert_thread_profile(db, **kwargs):
        assert kwargs["title"] == "RoPE 논문 탐색"
        return object()

    async def mock_create_event(db, *, thread_id, event_type, node_name, payload):
        assert event_type == "thread_title_ai_generated"
        return object()

    async def mock_get_thread_summary(db, thread_id, *, user_id):
        return summary

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(LoggingService, "get_or_create_session", mock_get_or_create_session)
    monkeypatch.setattr(ThreadProfileService, "get_thread_profile", mock_get_thread_profile)
    monkeypatch.setattr(ThreadService, "get_thread_title_policy_stats", mock_get_title_policy_stats)
    monkeypatch.setattr(ThreadTitleService, "generate_title", mock_generate_title)
    monkeypatch.setattr(ThreadProfileService, "upsert_thread_profile", mock_upsert_thread_profile)
    monkeypatch.setattr(TraceService, "create_event", mock_create_event)
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
    """Manual title override blocks AI overrides even on the first turn."""
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
    from services.thread_service import ThreadService, ThreadTitlePolicyStats
    from services.thread_title_service import ThreadTitleService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        return type("Session", (), {"user_id": "test-user"})()

    async def mock_get_thread_profile(db, thread_id, user_id):
        return type("Profile", (), {"title_override": "수동 제목"})()

    async def mock_get_title_policy_stats(db, thread_id):
        return ThreadTitlePolicyStats(
            user_turn_count=1,
            assistant_turn_count=0,
            ai_title_generation_count=0,
            has_manual_title_event=False,
        )

    async def mock_get_thread_summary(db, thread_id, *, user_id):
        return summary

    async def fail_generate_title(message):
        raise AssertionError("generate_title should not be called when manual title exists")

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(ThreadProfileService, "get_thread_profile", mock_get_thread_profile)
    monkeypatch.setattr(ThreadService, "get_thread_title_policy_stats", mock_get_title_policy_stats)
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


def test_generate_suggested_queries_persists_summary_and_returns_telemetry(monkeypatch):
    """Suggested-queries endpoint generates list, traces summary, returns telemetry."""
    from services.thread_service import ThreadService, ThreadSuggestionContext
    from services.thread_suggested_query_service import ThreadSuggestedQueryService
    from services.thread_telemetry_service import ThreadTelemetry, ThreadTelemetryService
    from services.trace_service import TraceService

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        return type("Session", (), {"user_id": "test-user"})()

    async def mock_get_latest_suggestion_context(db, thread_id):
        return ThreadSuggestionContext(
            user_content="RoPE 논문 설명해줘",
            assistant_content="RoPE 논문에 대한 최종 답변",
        )

    async def mock_generate_suggestions(*, user_message, assistant_message):
        return ["RoPE와 ALiBi 차이도 비교해줘", "대표 후속 연구 흐름도 정리해줘"]

    async def mock_create_event(db, *, thread_id, event_type, node_name, payload):
        assert event_type == "suggested_queries_summary"
        return object()

    async def mock_get_thread_telemetry(db, thread_id):
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
