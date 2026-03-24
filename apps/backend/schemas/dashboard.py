from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    user_id: str
    total_turns: int
    completed_turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_reasoning_tokens: int
    total_cost_microusd: int
    exact_total_cost_microusd: int
    estimated_total_cost_microusd: int
    exact_reasoning_cost_microusd: int
    estimated_reasoning_cost_microusd: int
    avg_latency_ms: int | None
    avg_ttft_ms: int | None
    total_tool_calls: int


class DashboardDailyUsagePointResponse(BaseModel):
    usage_date: date
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int
    total_cost_microusd: int


class DashboardDailyUsageResponse(BaseModel):
    user_id: str
    points: list[DashboardDailyUsagePointResponse]


class DashboardLiveTraceRowResponse(BaseModel):
    timestamp: datetime
    user_id: str
    thread_id: str
    turn_id: UUID
    turn_index: int
    request_kind: str
    model: str | None
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency_ms: int | None
    ttft_ms: int | None
    status: str
    active_team_final: str | None


class DashboardLiveTracesResponse(BaseModel):
    user_id: str
    rows: list[DashboardLiveTraceRowResponse]
