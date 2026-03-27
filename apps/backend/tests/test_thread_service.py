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
    assert message.role == "user"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(message)


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
    assert summary.created_at == created_at
    assert summary.last_activity_at == last_activity_at
    assert summary.message_count == 3
    assert summary.latest_status == "completed"
    assert summary.checkpoint_id == "cp-9"


def test_derive_status_prefers_status_trace_over_checkpoint_status():
    assert ThreadService._derive_status("errored", "completed") == "errored"
    assert ThreadService._derive_status(None, "interrupted") == "interrupted"
    assert ThreadService._derive_status(None, None) is None


def test_sort_thread_summaries_prioritizes_pinned_then_recent_activity():
    base_time = datetime(2026, 3, 21, 9, 0, 0)
    summaries = [
        ThreadService._apply_profile_overrides(
            ThreadService._build_summary(
                {
                    "thread_id": "thread-unpinned-new",
                    "first_user_content": "unpinned newer",
                    "latest_assistant_content": "answer",
                    "latest_user_content": "question",
                    "created_at": base_time,
                    "last_activity_at": base_time + timedelta(hours=3),
                    "message_count": 2,
                    "latest_status": "completed",
                    "checkpoint_status": None,
                    "checkpoint_id": "cp-1",
                }
            ),
            None,
        ),
        ThreadService._apply_profile_overrides(
            ThreadService._build_summary(
                {
                    "thread_id": "thread-pinned-older",
                    "first_user_content": "pinned older",
                    "latest_assistant_content": "answer",
                    "latest_user_content": "question",
                    "created_at": base_time,
                    "last_activity_at": base_time + timedelta(hours=1),
                    "message_count": 2,
                    "latest_status": "completed",
                    "checkpoint_status": None,
                    "checkpoint_id": "cp-2",
                }
            ),
            SimpleNamespace(
                title_override=None,
                pinned=True,
                archived=False,
            ),
        ),
        ThreadService._apply_profile_overrides(
            ThreadService._build_summary(
                {
                    "thread_id": "thread-pinned-newer",
                    "first_user_content": "pinned newer",
                    "latest_assistant_content": "answer",
                    "latest_user_content": "question",
                    "created_at": base_time,
                    "last_activity_at": base_time + timedelta(hours=2),
                    "message_count": 2,
                    "latest_status": "completed",
                    "checkpoint_status": None,
                    "checkpoint_id": "cp-3",
                }
            ),
            SimpleNamespace(
                title_override=None,
                pinned=True,
                archived=False,
            ),
        ),
    ]

    ordered = ThreadService._sort_thread_summaries(summaries)

    assert [summary.thread_id for summary in ordered] == [
        "thread-pinned-newer",
        "thread-pinned-older",
        "thread-unpinned-new",
    ]


@pytest.mark.asyncio
async def test_list_thread_summaries_executes_single_query_and_maps_rows():
    created_at = datetime(2026, 3, 21, 9, 0, 0)
    rows = [
        {
            "thread_id": "thread-a",
            "first_user_content": None,
            "latest_assistant_content": None,
            "latest_user_content": "   pending user message   ",
            "created_at": created_at,
            "last_activity_at": None,
            "message_count": 1,
            "latest_status": "interrupted",
            "checkpoint_status": "running",
            "checkpoint_id": None,
        }
    ]

    result = SimpleNamespace(
        mappings=lambda: SimpleNamespace(all=lambda: rows),
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    original_get_thread_profiles_map = ThreadProfileService.get_thread_profiles_map
    ThreadProfileService.get_thread_profiles_map = AsyncMock(return_value={})

    try:
        summaries = await ThreadService.list_thread_summaries(
            db, user_id="user-1", limit=10
        )
    finally:
        ThreadProfileService.get_thread_profiles_map = original_get_thread_profiles_map

    assert len(summaries) == 1
    assert summaries[0].thread_id == "thread-a"
    assert summaries[0].title == "Untitled chat"
    assert summaries[0].preview == "pending user message"
    assert summaries[0].last_activity_at == created_at
    assert summaries[0].latest_status == "interrupted"
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_thread_summaries_preserves_latest_first_order_and_counts():
    created_at = datetime(2026, 3, 21, 9, 0, 0)
    rows = [
        {
            "thread_id": "thread-newer",
            "first_user_content": "latest question",
            "latest_assistant_content": "latest answer",
            "latest_user_content": "latest question",
            "created_at": created_at + timedelta(hours=1),
            "last_activity_at": created_at + timedelta(hours=2),
            "message_count": 4,
            "latest_status": "completed",
            "checkpoint_status": "running",
            "checkpoint_id": "cp-newer",
        },
        {
            "thread_id": "thread-older",
            "first_user_content": "older question",
            "latest_assistant_content": None,
            "latest_user_content": "older question follow-up",
            "created_at": created_at,
            "last_activity_at": created_at + timedelta(minutes=15),
            "message_count": 2,
            "latest_status": None,
            "checkpoint_status": "interrupted",
            "checkpoint_id": "cp-older",
        },
    ]

    result = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    original_get_thread_profiles_map = ThreadProfileService.get_thread_profiles_map
    ThreadProfileService.get_thread_profiles_map = AsyncMock(return_value={})

    try:
        summaries = await ThreadService.list_thread_summaries(
            db, user_id="user-1", limit=5
        )
    finally:
        ThreadProfileService.get_thread_profiles_map = original_get_thread_profiles_map

    assert [summary.thread_id for summary in summaries] == [
        "thread-newer",
        "thread-older",
    ]
    assert summaries[0].message_count == 4
    assert summaries[1].preview == "older question follow-up"
    assert summaries[1].latest_status == "interrupted"


@pytest.mark.asyncio
async def test_get_thread_messages_maps_image_attachments_to_public_urls():
    message_id = uuid4()
    created_at = datetime(2026, 3, 21, 9, 0, 0)
    result = SimpleNamespace(
        mappings=lambda: SimpleNamespace(
            all=lambda: [
                {
                    "id": message_id,
                    "role": "user",
                    "content": "Look at this",
                    "created_at": created_at,
                    "attachments": [
                        {
                            "kind": "image",
                            "storage_path": "apps/backend/data/images/example.jpg",
                        }
                    ],
                }
            ]
        )
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    messages = await ThreadService.get_thread_messages(db, "thread-visual")

    assert len(messages) == 1
    assert messages[0].attachments[0].url == (
        f"/api/threads/thread-visual/messages/{message_id}/attachments/0"
    )
    assert messages[0].attachments[0].alt == "첨부 이미지 1"


@pytest.mark.asyncio
async def test_get_thread_messages_maps_document_attachments_to_public_urls():
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

    assert len(messages) == 1
    attachment = messages[0].attachments[0]
    assert attachment.kind == "pdf"
    assert attachment.file_name == "example.pdf"
    assert attachment.mime_type == "application/pdf"
    assert attachment.size_bytes == 2048
    assert attachment.url == (
        f"/api/threads/thread-doc/messages/{message_id}/attachments/0"
    )


@pytest.mark.asyncio
async def test_list_thread_summaries_places_pinned_threads_at_top():
    created_at = datetime(2026, 3, 21, 9, 0, 0)
    rows = [
        {
            "thread_id": "thread-unpinned",
            "first_user_content": "newer question",
            "latest_assistant_content": "newer answer",
            "latest_user_content": "newer question",
            "created_at": created_at,
            "last_activity_at": created_at + timedelta(hours=3),
            "message_count": 2,
            "latest_status": "completed",
            "checkpoint_status": None,
            "checkpoint_id": "cp-unpinned",
        },
        {
            "thread_id": "thread-pinned",
            "first_user_content": "older pinned",
            "latest_assistant_content": "older pinned answer",
            "latest_user_content": "older pinned",
            "created_at": created_at,
            "last_activity_at": created_at + timedelta(hours=1),
            "message_count": 2,
            "latest_status": "completed",
            "checkpoint_status": None,
            "checkpoint_id": "cp-pinned",
        },
    ]

    result = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    original_get_thread_profiles_map = ThreadProfileService.get_thread_profiles_map
    ThreadProfileService.get_thread_profiles_map = AsyncMock(
        return_value={
            "thread-pinned": SimpleNamespace(
                title_override=None,
                pinned=True,
                archived=False,
            )
        }
    )

    try:
        summaries = await ThreadService.list_thread_summaries(
            db, user_id="user-1", limit=5
        )
    finally:
        ThreadProfileService.get_thread_profiles_map = original_get_thread_profiles_map

    assert [summary.thread_id for summary in summaries] == [
        "thread-pinned",
        "thread-unpinned",
    ]


@pytest.mark.asyncio
async def test_get_thread_messages_maps_rows_in_created_order():
    first_id = uuid4()
    second_id = uuid4()
    rows = [
        {
            "id": first_id,
            "role": "user",
            "content": "first",
            "created_at": datetime(2026, 3, 21, 9, 0, 0),
        },
        {
            "id": second_id,
            "role": "assistant",
            "content": "second",
            "created_at": datetime(2026, 3, 21, 9, 1, 0),
        },
    ]
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    messages = await ThreadService.get_thread_messages(db, "thread-a")

    assert [message.id for message in messages] == [first_id, second_id]
    assert [message.role for message in messages] == ["user", "assistant"]


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
