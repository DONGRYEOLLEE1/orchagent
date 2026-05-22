from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from models.logging import KST, ChatSession
from services.logging_service import LoggingService
from services.thread_profile_service import ThreadProfileService
from services.thread_service import ThreadService


@pytest.mark.asyncio
async def test_log_message_updates_session_timestamp():
    """Logging a message must bump the parent session's updated_at."""
    old_time = KST.localize(datetime(2026, 3, 20, 12, 0, 0))
    session = ChatSession(id="thread-1", updated_at=old_time)
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = Mock()

    original_get_or_create_session = LoggingService.get_or_create_session
    LoggingService.get_or_create_session = AsyncMock(return_value=session)
    try:
        message = await LoggingService.log_message(
            db, "thread-1", role="user", content="hello", user_id="user-1"
        )
    finally:
        LoggingService.get_or_create_session = original_get_or_create_session

    assert session.updated_at > old_time
    assert message.session_id == "thread-1"


def test_build_summary_uses_phase_zero_derivation_rules():
    created_at = datetime(2026, 3, 21, 9, 0, 0)
    last_activity_at = created_at + timedelta(hours=1)
    row = {
        "thread_id": "thread-123",
        "first_user_content": "   first prompt becomes the title   ",
        "latest_assistant_content": " assistant answer ",
        "latest_user_content": " latest user prompt ",
        "created_at": created_at,
        "last_activity_at": last_activity_at,
        "message_count": 3,
        "latest_status": None,
        "checkpoint_status": "completed",
        "checkpoint_id": "cp-9",
    }

    summary = ThreadService._build_summary(row)

    assert summary.thread_id == "thread-123"
    assert summary.title == "first prompt becomes the title"
    assert summary.preview == "assistant answer"
    assert summary.message_count == 3
    assert summary.latest_status == "completed"


def test_derive_status_prefers_status_trace_over_checkpoint_status():
    assert ThreadService._derive_status("errored", "completed") == "errored"
    assert ThreadService._derive_status(None, "interrupted") == "interrupted"
    assert ThreadService._derive_status(None, None) is None


def test_sort_thread_summaries_prioritizes_pinned_then_recent_activity():
    """Pinned threads must surface above unpinned; pinned threads keep recency order."""
    base_time = datetime(2026, 3, 21, 9, 0, 0)

    def _summary(thread_id, last_offset_hours, pinned):
        return ThreadService._apply_profile_overrides(
            ThreadService._build_summary(
                {
                    "thread_id": thread_id,
                    "first_user_content": thread_id,
                    "latest_assistant_content": "answer",
                    "latest_user_content": "question",
                    "created_at": base_time,
                    "last_activity_at": base_time + timedelta(hours=last_offset_hours),
                    "message_count": 2,
                    "latest_status": "completed",
                    "checkpoint_status": None,
                    "checkpoint_id": "cp",
                }
            ),
            SimpleNamespace(title_override=None, pinned=pinned, archived=False)
            if pinned
            else None,
        )

    ordered = ThreadService._sort_thread_summaries(
        [
            _summary("thread-unpinned-new", 3, False),
            _summary("thread-pinned-older", 1, True),
            _summary("thread-pinned-newer", 2, True),
        ]
    )

    assert [summary.thread_id for summary in ordered] == [
        "thread-pinned-newer",
        "thread-pinned-older",
        "thread-unpinned-new",
    ]


@pytest.mark.asyncio
async def test_get_thread_messages_maps_attachments_to_public_urls():
    """ThreadService must rewrite raw storage_path into a public attachment URL."""
    message_id = uuid4()
    created_at = datetime(2026, 3, 21, 9, 0, 0)
    result = SimpleNamespace(
        mappings=lambda: SimpleNamespace(
            all=lambda: [
                {
                    "id": message_id,
                    "role": "user",
                    "content": "Analyze this PDF",
                    "created_at": created_at,
                    "attachments": [
                        {
                            "kind": "pdf",
                            "storage_path": "apps/backend/data/uploads/pdf/example.pdf",
                            "file_name": "example.pdf",
                            "mime_type": "application/pdf",
                            "size_bytes": 2048,
                        }
                    ],
                }
            ]
        )
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    messages = await ThreadService.get_thread_messages(db, "thread-doc")

    attachment = messages[0].attachments[0]
    assert attachment.kind == "pdf"
    assert attachment.file_name == "example.pdf"
    assert attachment.url == (
        f"/api/threads/thread-doc/messages/{message_id}/attachments/0"
    )


@pytest.mark.asyncio
async def test_delete_thread_cleans_turn_dependencies_before_session_delete():
    """delete_thread must purge turn FK dependencies before removing the session row."""
    db = AsyncMock()
    session = SimpleNamespace(id="thread-delete", user_id="user-1")

    original_get_chat_session = ThreadService.get_chat_session
    ThreadService.get_chat_session = AsyncMock(return_value=session)
    db.execute.side_effect = (
        [SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [uuid4(), uuid4()]))]
        + [None] * 20
    )
    try:
        deleted = await ThreadService.delete_thread(
            db,
            "thread-delete",
            user_id="user-1",
        )
    finally:
        ThreadService.get_chat_session = original_get_chat_session

    assert deleted is True
    assert db.execute.await_count >= 5
    assert db.delete.await_count == 1
    assert db.delete.await_args.args[0] is session
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_get_thread_detail_returns_none_when_summary_is_missing():
    db = AsyncMock()

    original_get_thread_summary = ThreadService.get_thread_summary
    ThreadService.get_thread_summary = AsyncMock(return_value=None)
    try:
        detail = await ThreadService.get_thread_detail(
            db, "missing-thread", user_id="user-1"
        )
    finally:
        ThreadService.get_thread_summary = original_get_thread_summary

    assert detail is None
