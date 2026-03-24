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
    turn = ChatTurn(
        id=uuid4(),
        thread_id="thread-1",
        user_id="user-1",
        turn_index=5,
        request_kind="chat",
        status="running",
        started_at=started_at,
        trace_id="trace-1",
    )
    mock_db.refresh = AsyncMock(side_effect=lambda instance: None)

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
async def test_mark_first_token_sets_ttft():
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    first_token_at = started_at + timedelta(milliseconds=320)
    turn = ChatTurn(
        id=uuid4(),
        thread_id="thread-1",
        user_id="user-1",
        turn_index=1,
        request_kind="chat",
        status="running",
        started_at=started_at,
        trace_id="trace-1",
    )
    mock_db = AsyncMock()
    mock_db.get.return_value = turn

    updated = await ChatAnalyticsService.mark_first_token(
        mock_db, turn.id, first_token_at
    )

    assert updated is turn
    assert turn.first_token_at == first_token_at
    assert turn.ttft_ms == 320
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_turn_sets_completed_latency_and_summary_fields():
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

    updated = await ChatAnalyticsService.finalize_turn(
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

    assert updated is turn
    assert turn.status == "completed"
    assert turn.latency_ms == 4250
    assert turn.ttft_ms == 500
    assert turn.final_checkpoint_id == "cp-1"
    assert turn.final_status_node == "finalizer"
    assert turn.assistant_char_count == 128
    assert turn.tool_call_count == 2


@pytest.mark.asyncio
async def test_finalize_turn_marks_interrupted():
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    interrupted_at = started_at + timedelta(seconds=2)
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

    await ChatAnalyticsService.finalize_turn(
        mock_db,
        ChatTurnFinalizeParams(
            turn_id=turn.id,
            status="interrupted",
            interrupted_at=interrupted_at,
            metadata={"resume_action": "approve"},
        ),
    )

    assert turn.status == "interrupted"
    assert turn.interrupted_at == interrupted_at
    assert turn.metadata_json == {"resume_action": "approve"}


@pytest.mark.asyncio
async def test_finalize_turn_marks_errored():
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    errored_at = started_at + timedelta(seconds=1)
    turn = ChatTurn(
        id=uuid4(),
        thread_id="thread-1",
        user_id="user-1",
        turn_index=3,
        request_kind="chat",
        status="running",
        started_at=started_at,
        trace_id="trace-3",
    )
    mock_db = AsyncMock()
    mock_db.get.return_value = turn

    await ChatAnalyticsService.finalize_turn(
        mock_db,
        ChatTurnFinalizeParams(
            turn_id=turn.id,
            status="errored",
            errored_at=errored_at,
            metadata={"error_message": "boom"},
        ),
    )

    assert turn.status == "errored"
    assert turn.errored_at == errored_at
    assert turn.metadata_json == {"error_message": "boom"}
