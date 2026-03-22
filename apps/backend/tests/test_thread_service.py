from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from models.logging import KST, ChatSession
from services.logging_service import LoggingService
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
            db, "thread-1", role="user", content="hello"
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

    summaries = await ThreadService.list_thread_summaries(db, limit=10)

    assert len(summaries) == 1
    assert summaries[0].thread_id == "thread-a"
    assert summaries[0].title == "Untitled chat"
    assert summaries[0].preview == "pending user message"
    assert summaries[0].last_activity_at == created_at
    assert summaries[0].latest_status == "interrupted"
    db.execute.assert_awaited_once()
