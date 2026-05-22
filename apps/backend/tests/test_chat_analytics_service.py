from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from models.analytics import ChatTurn
from services.chat_analytics_service import (
    ChatAnalyticsService,
    ChatTurnFinalizeParams,
    ChatTurnStartParams,
)


@pytest.mark.asyncio
async def test_start_turn_assigns_next_turn_index():
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.scalar.return_value = 4

    async def fake_refresh(instance):
        instance.turn_index = 5

    mock_db.refresh = fake_refresh

    created = await ChatAnalyticsService.start_turn(
        mock_db,
        ChatTurnStartParams(
            thread_id="thread-1",
            user_id="user-1",
            request_kind="chat",
            request_message_id=None,
            started_at=started_at,
            trace_id="trace-1",
            metadata={"message_length": 10},
        ),
    )

    assert created.turn_index == 5
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_turn_sets_completed_latency_and_summary_fields():
    """Completion path must compute latency and persist summary fields."""
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    completed_at = started_at + timedelta(seconds=4, milliseconds=250)
    turn = ChatTurn(
        id=uuid4(),
        thread_id="thread-1",
        user_id="user-1",
        turn_index=1,
        request_kind="chat",
        status="running",
        started_at=started_at,
        first_token_at=started_at + timedelta(milliseconds=500),
        trace_id="trace-1",
    )
    mock_db = AsyncMock()
    mock_db.get.return_value = turn

    await ChatAnalyticsService.finalize_turn(
        mock_db,
        ChatTurnFinalizeParams(
            turn_id=turn.id,
            status="completed",
            completed_at=completed_at,
            final_checkpoint_id="cp-1",
            final_status_node="finalizer",
            response_mode="finalizer",
            active_team_final="research",
            assistant_char_count=128,
            tool_call_count=2,
            metadata={"disconnected": False},
        ),
    )

    assert turn.status == "completed"
    assert turn.latency_ms == 4250
    assert turn.ttft_ms == 500
    assert turn.tool_call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,timestamp_field,metadata",
    [
        ("interrupted", "interrupted_at", {"resume_action": "approve"}),
        ("errored", "errored_at", {"error_message": "boom"}),
    ],
)
async def test_finalize_turn_marks_non_completed_status(status, timestamp_field, metadata):
    """Interrupted/errored finalizations must set the matching timestamp and metadata."""
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    event_at = started_at + timedelta(seconds=2)
    turn = ChatTurn(
        id=uuid4(),
        thread_id="thread-1",
        user_id="user-1",
        turn_index=2,
        request_kind="resume",
        status="running",
        started_at=started_at,
        trace_id="trace-2",
    )
    mock_db = AsyncMock()
    mock_db.get.return_value = turn

    params_kwargs = {
        "turn_id": turn.id,
        "status": status,
        "metadata": metadata,
        timestamp_field: event_at,
    }
    await ChatAnalyticsService.finalize_turn(mock_db, ChatTurnFinalizeParams(**params_kwargs))

    assert turn.status == status
    assert getattr(turn, timestamp_field) == event_at
    assert turn.metadata_json == metadata
