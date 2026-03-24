from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from models.analytics import ChatTurn, LLMUsageEvent
from services.dashboard_service import DashboardService


@pytest.mark.asyncio
async def test_dashboard_summary_aggregates_turn_and_usage_metrics(monkeypatch):
    turns = [
        ChatTurn(
            id=uuid4(),
            thread_id="thread-1",
            user_id="user-1",
            turn_index=1,
            request_kind="chat",
            status="completed",
            started_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
            latency_ms=1200,
            ttft_ms=300,
            tool_call_count=2,
            trace_id="trace-1",
        ),
        ChatTurn(
            id=uuid4(),
            thread_id="thread-2",
            user_id="user-1",
            turn_index=2,
            request_kind="resume",
            status="completed",
            started_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
            latency_ms=1800,
            ttft_ms=500,
            tool_call_count=1,
            trace_id="trace-2",
        ),
    ]
    usage_events = [
        LLMUsageEvent(
            id=uuid4(),
            user_id="user-1",
            thread_id="thread-1",
            turn_id=turns[0].id,
            provider="openai",
            model="gpt-5.4-mini",
            input_tokens=100,
            output_tokens=200,
            total_tokens=300,
            cache_read_input_tokens=0,
            cache_write_input_tokens=0,
            reasoning_output_tokens=50,
            text_output_tokens=150,
            usage_metadata={},
            total_cost_microusd=1000,
            reasoning_cost_microusd=None,
            estimated_reasoning_cost_microusd=250,
            cost_is_estimated=False,
            reasoning_cost_is_estimated=True,
            created_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
        ),
        LLMUsageEvent(
            id=uuid4(),
            user_id="user-1",
            thread_id="thread-2",
            turn_id=turns[1].id,
            provider="openai",
            model="gpt-5.4-mini",
            input_tokens=80,
            output_tokens=120,
            total_tokens=200,
            cache_read_input_tokens=0,
            cache_write_input_tokens=0,
            reasoning_output_tokens=30,
            text_output_tokens=90,
            usage_metadata={},
            total_cost_microusd=700,
            reasoning_cost_microusd=None,
            estimated_reasoning_cost_microusd=175,
            cost_is_estimated=False,
            reasoning_cost_is_estimated=True,
            created_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
        ),
    ]

    async def mock_load_turns(*args, **kwargs):
        return turns

    async def mock_load_usage(*args, **kwargs):
        start_at = kwargs.get("start_at")
        end_at = kwargs.get("end_at")
        return [
            event
            for event in usage_events
            if (start_at is None or event.created_at >= start_at)
            and (end_at is None or event.created_at < end_at)
        ]

    monkeypatch.setattr(DashboardService, "_load_turns", mock_load_turns)
    monkeypatch.setattr(DashboardService, "_load_usage_events", mock_load_usage)

    summary = await DashboardService.get_summary(object(), user_id="user-1")

    assert summary.total_turns == 2
    assert summary.completed_turns == 2
    assert summary.total_tokens == 500
    assert summary.total_reasoning_tokens == 80
    assert summary.total_cost_microusd == 1700
    assert summary.estimated_reasoning_cost_microusd == 425
    assert summary.avg_latency_ms == 1500
    assert summary.avg_ttft_ms == 400
    assert summary.total_tool_calls == 3


@pytest.mark.asyncio
async def test_dashboard_daily_usage_respects_date_range(monkeypatch):
    usage_events = [
        LLMUsageEvent(
            id=uuid4(),
            user_id="user-1",
            thread_id="thread-1",
            turn_id=uuid4(),
            provider="openai",
            model="gpt-5.4-mini",
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            cache_read_input_tokens=0,
            cache_write_input_tokens=0,
            reasoning_output_tokens=5,
            text_output_tokens=15,
            usage_metadata={},
            total_cost_microusd=100,
            created_at=datetime(2026, 3, 23, 10, 0, tzinfo=UTC),
        ),
        LLMUsageEvent(
            id=uuid4(),
            user_id="user-1",
            thread_id="thread-1",
            turn_id=uuid4(),
            provider="openai",
            model="gpt-5.4-mini",
            input_tokens=40,
            output_tokens=60,
            total_tokens=100,
            cache_read_input_tokens=0,
            cache_write_input_tokens=0,
            reasoning_output_tokens=15,
            text_output_tokens=45,
            usage_metadata={},
            total_cost_microusd=300,
            created_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
        ),
    ]

    async def mock_load_usage(*args, **kwargs):
        start_at = kwargs.get("start_at")
        end_at = kwargs.get("end_at")
        return [
            event
            for event in usage_events
            if (start_at is None or event.created_at >= start_at)
            and (end_at is None or event.created_at < end_at)
        ]

    monkeypatch.setattr(DashboardService, "_load_usage_events", mock_load_usage)

    points = await DashboardService.get_daily_usage_series(
        object(),
        user_id="user-1",
        start_date=date(2026, 3, 24),
        end_date=date(2026, 3, 24),
    )

    assert len(points) == 1
    assert points[0].usage_date == date(2026, 3, 24)
    assert points[0].total_tokens == 100


@pytest.mark.asyncio
async def test_dashboard_live_traces_combines_latest_usage_per_turn(monkeypatch):
    turn_id = uuid4()
    turns = [
        ChatTurn(
            id=turn_id,
            thread_id="thread-1",
            user_id="user-1",
            turn_index=3,
            request_kind="chat",
            status="completed",
            started_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
            latency_ms=900,
            ttft_ms=250,
            active_team_final="research",
            trace_id="trace-1",
        )
    ]
    usage_events = [
        LLMUsageEvent(
            id=uuid4(),
            user_id="user-1",
            thread_id="thread-1",
            turn_id=turn_id,
            provider="openai",
            model="gpt-5.4-mini",
            input_tokens=12,
            output_tokens=34,
            total_tokens=46,
            cache_read_input_tokens=0,
            cache_write_input_tokens=0,
            reasoning_output_tokens=11,
            text_output_tokens=23,
            usage_metadata={},
            total_cost_microusd=0,
            created_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
        )
    ]

    async def mock_load_turns(*args, **kwargs):
        return turns

    async def mock_load_usage(*args, **kwargs):
        return usage_events

    monkeypatch.setattr(DashboardService, "_load_turns", mock_load_turns)
    monkeypatch.setattr(DashboardService, "_load_usage_events", mock_load_usage)

    rows = await DashboardService.get_live_traces(object(), user_id="user-1")

    assert len(rows) == 1
    assert rows[0].model == "gpt-5.4-mini"
    assert rows[0].input_tokens == 12
    assert rows[0].reasoning_tokens == 11
