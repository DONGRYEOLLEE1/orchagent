from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from models.analytics import ToolExecutionEvent
from services.chat_analytics_service import (
    ChatAnalyticsService,
    ToolExecutionFinishParams,
    ToolExecutionStartParams,
)


@pytest.mark.asyncio
async def test_create_tool_execution_persists_running_row():
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    created = await ChatAnalyticsService.create_tool_execution(
        mock_db,
        ToolExecutionStartParams(
            user_id="user-1",
            thread_id="thread-1",
            turn_id=uuid4(),
            run_id="tool-run",
            trace_id="trace-1",
            span_id="tool-run",
            parent_span_id=None,
            node_name="tavily_tool",
            tool_name="tavily_tool",
            display_name="Tavily Tool",
            started_at=started_at,
            input_summary={"query": "latest ai"},
        ),
    )

    assert created.status == "running"
    assert created.input_summary == {"query": "latest ai"}
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_finish_tool_execution_marks_success():
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    ended_at = started_at + timedelta(milliseconds=850)
    tool_event = ToolExecutionEvent(
        id=uuid4(),
        user_id="user-1",
        thread_id="thread-1",
        turn_id=uuid4(),
        run_id="tool-run",
        trace_id="trace-1",
        span_id="tool-run",
        parent_span_id=None,
        node_name="tavily_tool",
        tool_name="tavily_tool",
        display_name="Tavily Tool",
        status="running",
        started_at=started_at,
    )
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tool_event
    mock_db.execute.return_value = mock_result

    updated = await ChatAnalyticsService.finish_tool_execution(
        mock_db,
        ToolExecutionFinishParams(
            thread_id="thread-1",
            turn_id=tool_event.turn_id,
            run_id="tool-run",
            tool_name="tavily_tool",
            status="success",
            ended_at=ended_at,
            output_summary={"results": 3},
        ),
    )

    assert updated is tool_event
    assert tool_event.status == "success"
    assert tool_event.duration_ms == 850
    assert tool_event.output_summary == {"results": 3}


@pytest.mark.asyncio
async def test_finish_tool_execution_marks_error():
    started_at = datetime(2026, 3, 24, 8, 0, tzinfo=UTC)
    ended_at = started_at + timedelta(milliseconds=220)
    tool_event = ToolExecutionEvent(
        id=uuid4(),
        user_id="user-1",
        thread_id="thread-1",
        turn_id=uuid4(),
        run_id="tool-run",
        trace_id="trace-1",
        span_id="tool-run",
        parent_span_id=None,
        node_name="tavily_tool",
        tool_name="tavily_tool",
        display_name="Tavily Tool",
        status="running",
        started_at=started_at,
    )
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tool_event
    mock_db.execute.return_value = mock_result

    updated = await ChatAnalyticsService.finish_tool_execution(
        mock_db,
        ToolExecutionFinishParams(
            thread_id="thread-1",
            turn_id=tool_event.turn_id,
            run_id="tool-run",
            tool_name="tavily_tool",
            status="error",
            ended_at=ended_at,
            error_summary={"message": "timeout"},
        ),
    )

    assert updated is tool_event
    assert tool_event.status == "error"
    assert tool_event.duration_ms == 220
    assert tool_event.error_summary == {"message": "timeout"}
