from datetime import date, datetime, UTC
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from main import app
from services.dashboard_service import DailyUsagePoint, DashboardService, DashboardSummary, LiveTraceRow
from services.security_service import get_current_user

client = TestClient(app)


def test_dashboard_summary_returns_current_user_metrics(monkeypatch):
    async def mock_summary(*args, **kwargs):
        return DashboardSummary(
            user_id="test-user",
            total_turns=3,
            completed_turns=2,
            total_input_tokens=10,
            total_output_tokens=20,
            total_tokens=30,
            total_reasoning_tokens=5,
            total_cost_microusd=100,
            exact_total_cost_microusd=100,
            estimated_total_cost_microusd=0,
            exact_reasoning_cost_microusd=0,
            estimated_reasoning_cost_microusd=25,
            avg_latency_ms=1000,
            avg_ttft_ms=300,
            total_tool_calls=4,
        )

    monkeypatch.setattr(DashboardService, "get_summary", mock_summary)

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "test-user"
    assert body["total_tokens"] == 30


def test_dashboard_daily_usage_returns_points(monkeypatch):
    async def mock_daily(*args, **kwargs):
        return [
            DailyUsagePoint(
                usage_date=date(2026, 3, 24),
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                reasoning_tokens=5,
                total_cost_microusd=100,
            )
        ]

    monkeypatch.setattr(DashboardService, "get_daily_usage_series", mock_daily)

    response = client.get("/api/dashboard/daily-usage")

    assert response.status_code == 200
    body = response.json()
    assert body["points"][0]["usage_date"] == "2026-03-24"


def test_dashboard_live_traces_returns_rows(monkeypatch):
    async def mock_live(*args, **kwargs):
        return [
            LiveTraceRow(
                timestamp=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
                user_id="test-user",
                thread_id="thread-1",
                turn_id=uuid4(),
                turn_index=1,
                request_kind="chat",
                model="gpt-5.4-mini",
                input_tokens=10,
                output_tokens=20,
                reasoning_tokens=5,
                latency_ms=1000,
                ttft_ms=300,
                status="completed",
                active_team_final="research",
            )
        ]

    monkeypatch.setattr(DashboardService, "get_live_traces", mock_live)

    response = client.get("/api/dashboard/live-traces?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["model"] == "gpt-5.4-mini"


def test_dashboard_forbids_non_admin_cross_user_lookup():
    response = client.get("/api/dashboard/summary?user_id=someone-else")
    assert response.status_code == 403


def test_dashboard_allows_admin_cross_user_lookup(monkeypatch):
    async def override_current_user():
        return SimpleNamespace(id="admin-user", role="admin")

    async def mock_summary(*args, **kwargs):
        return DashboardSummary(
            user_id="someone-else",
            total_turns=1,
            completed_turns=1,
            total_input_tokens=1,
            total_output_tokens=1,
            total_tokens=2,
            total_reasoning_tokens=0,
            total_cost_microusd=0,
            exact_total_cost_microusd=0,
            estimated_total_cost_microusd=0,
            exact_reasoning_cost_microusd=0,
            estimated_reasoning_cost_microusd=0,
            avg_latency_ms=100,
            avg_ttft_ms=50,
            total_tool_calls=0,
        )

    monkeypatch.setattr(DashboardService, "get_summary", mock_summary)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = client.get("/api/dashboard/summary?user_id=someone-else")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 200
    assert response.json()["user_id"] == "someone-else"
