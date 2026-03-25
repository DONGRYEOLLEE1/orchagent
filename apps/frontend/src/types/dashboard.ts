export interface DashboardSummary {
  user_id: string;
  total_turns: number;
  completed_turns: number;
  total_llm_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_reasoning_tokens: number;
  total_cost_microusd: number;
  exact_total_cost_microusd: number;
  estimated_total_cost_microusd: number;
  exact_reasoning_cost_microusd: number;
  estimated_reasoning_cost_microusd: number;
  avg_latency_ms: number | null;
  avg_ttft_ms: number | null;
  total_tool_calls: number;
  total_inference_cost_microusd: number;
}

export interface DashboardDailyUsagePoint {
  usage_date: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  reasoning_tokens: number;
  total_cost_microusd: number;
}

export interface DashboardDailyUsageResponse {
  user_id: string;
  points: DashboardDailyUsagePoint[];
}

export interface DashboardLiveTraceRow {
  timestamp: string;
  user_id: string;
  thread_id: string;
  turn_id: string;
  turn_index: number;
  request_kind: string;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  latency_ms: number | null;
  ttft_ms: number | null;
  status: string;
  active_team_final: string | null;
}

export interface DashboardLiveTracesResponse {
  user_id: string;
  rows: DashboardLiveTraceRow[];
}
