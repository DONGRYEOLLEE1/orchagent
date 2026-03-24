---
작업명: User Tracing Analytics Schema Plan
간단요약: user별 LLM usage, reasoning tokens, latency, tool execution, raw trace를 정확히 적재할 수 있도록 DB schema와 수집 파이프라인을 확장하고, 이후 Dashboard 시각화를 위한 집계 계층을 설계한다.
작성일시: 2026-03-24 17:08 KST
최종 수정일시: 2026-03-24 17:28 KST
---

# User Tracing Analytics Schema Plan

## 목표

- 유저별로 thread/turn/model/tool/trace 단위의 관측 데이터를 DB에 정확히 저장한다.
- `response.usage_metadata`에 포함되는 실제 토큰 메타데이터를 적재한다.
- `reasoning tokens`, `cache read tokens`, `latency`, `turn status`를 추정치가 아니라 가능한 한 실제 런타임 기준으로 기록한다.
- 이후 프론트 `Dashboard`에서 다음 지표를 바로 그릴 수 있는 구조를 만든다.
  - 유저별 총 토큰
  - 질의 -> 최종 AI 답변까지의 평균 시간
  - 총 추론 비용
  - 날짜별 토큰 사용량 그래프
  - 실시간 user tracing 테이블

## 현재 구조 진단

### 현재 장점

- `chat_sessions`, `chat_messages`, `trace_events`가 이미 존재해서 thread/message/raw trace 축은 있다.
- `auth_users`가 있고 `chat_sessions.user_id`가 있어 user ownership은 이미 분리된다.
- `trace_events`에 SSE/graph/tool/status/checkpoint 정보가 일부 저장된다.
- `usage.jsonl`에는 `user_id`, `model`, `prompt_tokens`, `completion_tokens`가 남는다.

### 현재 한계

- `usage.jsonl`는 DB가 아니라 파일이며, Dashboard의 canonical source로 쓰기 어렵다.
- `usage.jsonl`의 토큰 수는 [chat.py](/Users/drlee/workspace/orchagent/apps/backend/api/routes/chat.py)에서 `len(... ) // 4` 추정치다.
- `reasoning tokens`와 `cache_read tokens`가 DB에 저장되지 않는다.
- `trace_events`는 `thread_id` 중심 raw JSONB라 user/turn/model 기준 집계가 비효율적이다.
- `질의 -> 최종 답변 latency`를 정확히 계산할 turn-grain 테이블이 없다.
- tool start/end는 raw trace로만 남아 있어서 dashboard용 정규화 테이블이 없다.
- 모델 가격 변경 이력을 추적하지 않아 historical cost 재현이 어렵다.

## 핵심 설계 원칙

- raw trace와 dashboard용 정규화 테이블을 분리한다.
- `thread/session` 축과 `trace/span` 축을 분리한다.
- 집계에 필요한 key는 모든 fact 테이블에 명시적으로 중복 저장한다.
  - `user_id`
  - `thread_id`
  - `turn_id`
- 장기적으로 analytics sink/warehouse로 복제할 수 있게 key를 충분히 남긴다.
- 비용 계산은 write-time에 snapshot 기반으로 저장한다.
- reasoning cost가 모델 가격표상 독립 항목이 아닐 수 있으므로, `정확 비용`과 `추정 reasoning cost`를 구분한다.
- file logger는 보조 디버그 채널로만 남기고, DB를 canonical source로 승격한다.

## Phase 0 계약 고정

### turn 정의

- Dashboard V1에서 `turn`은 `/api/chat` 또는 `/api/chat/resume` 한 번의 호출 lifecycle을 뜻한다.
- turn은 사용자 입력 저장 시점부터 시작해서 아래 중 하나로 종료된다.
  - 최종 assistant 답변 저장 후 `completed`
  - HITL 대기 진입 시 `interrupted`
  - 예외 종료 시 `errored`
- thread title generation, suggested queries generation 같은 보조 LLM 호출은 schema에서 `request_kind`로 수용할 수 있게 설계하되, V1 Dashboard 집계 기준에는 포함하지 않는다.
  이유: 현재 우선 목표는 최종 답변 경로의 exact usage/latency/cost를 먼저 canonicalize하는 것이다.

### 비용 표기 정책

- `총 비용`은 pricing snapshot이 존재하는 usage row만 합산한다.
- `총 추론 비용`은 아래 우선순위를 따른다.
  - 1순위: 모델별 reasoning output 가격이 분리되어 있으면 `exact reasoning cost`
  - 2순위: 분리 가격이 없으면 `estimated reasoning cost`
    - 계산 방식: `output_cost_microusd * (reasoning_output_tokens / output_tokens)`
- Dashboard summary/API는 exact와 estimated를 섞어서 숨기지 않는다.
  - `exact_total_cost_microusd`
  - `estimated_total_cost_microusd`
  - `exact_reasoning_cost_microusd`
  - `estimated_reasoning_cost_microusd`

### canonical source 정책

- `usage.jsonl`, `session.jsonl`, `user.jsonl`는 개발/운영 디버그용 보조 로그다.
- Dashboard, tracing table, 집계 API의 canonical source는 Postgres fact table이다.

### Dashboard V1 범위

- 총 토큰
- 평균 latency
- 평균 TTFT
- 총 비용
- 총 추론 비용
- 날짜별 토큰 사용량 그래프
- 최신 turn tracing table

### trace/span 식별자 정책

- `chat_turns.id`를 Dashboard 관점의 root trace key로 사용한다.
- `trace_id`는 기본적으로 `chat_turns.id` 문자열 값과 동일하게 저장한다.
- LangChain/LangGraph `run_id`는 span-level 식별자로 저장한다.
- `span_id = run_id`, `parent_span_id`는 현재 단계에서는 nullable로 두고 추후 richer lineage가 필요할 때 보강한다.

## 엄격 검증 원칙

- 이 작업은 analytics와 cost 지표의 기준 데이터를 다루므로, “테스트가 몇 개 통과했다” 수준으로는 충분하지 않다.
- 각 phase는 아래 검증을 모두 통과해야 완료로 간주한다.

### 공통 strict validation 기준

- schema 변경은 모델 import 확인만으로 끝내지 않고 실제 table 생성/조회 smoke test를 통과해야 한다.
- token/cost 계산은 deterministic unit test로 exact 값을 검증해야 한다.
- latency/TTFT는 timestamp ordering과 null edge case를 모두 포함해 검증해야 한다.
- dashboard aggregate는 fixture 기반 expected total과 exact 일치해야 한다.
- interrupted/errored/disconnect/retry/resume 경로를 반드시 별도 케이스로 검증해야 한다.
- backfill 로직이 들어가면 idempotency test를 반드시 추가해야 한다.
- raw trace와 normalized fact 간 referential consistency를 검증해야 한다.

### 권장 검증 레이어

- unit test
  - 계산 함수, normalization, pricing math, token breakdown
- service test
  - turn lifecycle, usage write, tool execution write
- API test
  - dashboard endpoints, auth/permission, filters, date range
- integration/smoke test
  - 실제 `/api/chat` turn 1회 후 `chat_turns`, `llm_usage_events`, `tool_execution_events`, `trace_events`가 기대 형태로 저장되는지
- regression test
  - 기존 streaming, thread list, title generation, suggested queries가 깨지지 않는지

### 배포 전 최종 체크

- 1개 유저, 다중 thread, 다중 turn fixture로 dashboard aggregate 수치를 수동 계산과 대조
- reasoning-heavy query와 no-tool query를 각각 돌려 token/cost/latency 차이가 올바르게 집계되는지 확인
- Postgres만 사용하는 환경과 향후 analytics sink 전환을 모두 고려해 primary key / foreign key / index 설계를 검토

## 연구 기반 보강 포인트

공개 사례 조사 기준:

- OpenAI Agents SDK, LangSmith, Langfuse, Phoenix는 모두 `trace/span(run/observation)` 중심 모델을 가진다.
- Langfuse, Helicone 계열은 `user_id`, `session_id`, `trace_id`를 모든 telemetry에 전파하는 방향이 강하다.
- Phoenix는 `usage_metadata.output_token_details.reasoning`, `prompt_details.cache_read` 같은 세부 token breakdown을 first-class로 다룬다.
- Langfuse/Helicone는 analytics 저장소 분리를 전제로 하거나 강하게 시사한다.

따라서 본 계획에서는 다음을 추가 원칙으로 둔다.

- `chat_turns`는 thread-based conversation fact이면서 동시에 trace-level root fact 역할을 한다.
- `llm_usage_events`, `tool_execution_events`, `trace_events`에는 `trace_id`, `span_id` 또는 최소한 `run_id` 계열 식별자를 남긴다.
- 초기 구현은 Postgres canonical source로 시작하되, schema는 `ClickHouse`/DWH 적재를 방해하지 않도록 설계한다.
- raw payload JSONB는 보존하되, dashboard 핵심 축은 반드시 top-level typed column으로 승격한다.

## 추천 데이터 모델

### 1. `chat_turns`

turn 단위의 핵심 fact 테이블. Dashboard에서 평균 latency, 상태, turn 수, thread별 진행률을 계산하는 기준축이다.

권장 컬럼:

- `id UUID PK`
- `thread_id STRING NOT NULL FK -> chat_sessions.id`
- `user_id STRING NOT NULL FK -> auth_users.id`
- `turn_index INTEGER NOT NULL`
- `request_message_id UUID NULL FK -> chat_messages.id`
- `response_message_id UUID NULL FK -> chat_messages.id`
- `request_kind STRING NOT NULL`
  - 예: `chat`, `resume`, `title_generation`, `suggested_queries`
- `status STRING NOT NULL`
  - 예: `running`, `completed`, `errored`, `interrupted`
- `started_at TIMESTAMPTZ NOT NULL`
- `first_token_at TIMESTAMPTZ NULL`
- `completed_at TIMESTAMPTZ NULL`
- `interrupted_at TIMESTAMPTZ NULL`
- `errored_at TIMESTAMPTZ NULL`
- `latency_ms BIGINT NULL`
- `ttft_ms BIGINT NULL`
- `final_checkpoint_id STRING NULL`
- `final_status_node STRING NULL`
- `response_mode STRING NULL`
- `active_team_final STRING NULL`
- `active_worker_final STRING NULL`
- `trace_id STRING NULL`
- `assistant_char_count INTEGER NOT NULL DEFAULT 0`
- `tool_call_count INTEGER NOT NULL DEFAULT 0`
- `metadata JSONB NULL`

인덱스 권장:

- `(user_id, started_at DESC)`
- `(thread_id, turn_index DESC)`
- `(status, started_at DESC)`

### 2. `llm_usage_events`

모든 LLM 호출 단위의 usage fact 테이블. `response.usage_metadata`를 가능한 한 원형에 가깝게 저장한다.

권장 컬럼:

- `id UUID PK`
- `user_id STRING NOT NULL`
- `thread_id STRING NOT NULL`
- `turn_id UUID NOT NULL FK -> chat_turns.id`
- `run_id STRING NULL`
- `trace_id STRING NULL`
- `span_id STRING NULL`
- `parent_span_id STRING NULL`
- `node_name STRING NULL`
- `provider STRING NOT NULL`
- `model STRING NOT NULL`
- `request_role STRING NULL`
  - 예: `finalizer`, `head_supervisor`, `thread_title`, `suggested_queries`
- `input_tokens INTEGER NOT NULL DEFAULT 0`
- `output_tokens INTEGER NOT NULL DEFAULT 0`
- `total_tokens INTEGER NOT NULL DEFAULT 0`
- `cache_read_input_tokens INTEGER NOT NULL DEFAULT 0`
- `cache_write_input_tokens INTEGER NOT NULL DEFAULT 0`
- `reasoning_output_tokens INTEGER NOT NULL DEFAULT 0`
- `text_output_tokens INTEGER NOT NULL DEFAULT 0`
- `usage_metadata JSONB NOT NULL`
- `pricing_snapshot_id UUID NULL FK -> llm_pricing_snapshots.id`
- `input_cost_microusd BIGINT NOT NULL DEFAULT 0`
- `output_cost_microusd BIGINT NOT NULL DEFAULT 0`
- `reasoning_cost_microusd BIGINT NULL`
- `total_cost_microusd BIGINT NOT NULL DEFAULT 0`
- `created_at TIMESTAMPTZ NOT NULL`

중요 포인트:

- `usage_metadata.output_token_details.reasoning`를 `reasoning_output_tokens`로 정규화 저장한다.
- reasoning 가격이 독립 과금이면 `reasoning_cost_microusd`를 정확히 저장한다.
- reasoning 가격이 독립 과금이 아니면:
  - `reasoning_output_tokens`는 정확히 저장
  - `reasoning_cost_microusd`는 `NULL` 또는 `estimated_reasoning_cost_microusd` 별도 컬럼으로 분리

인덱스 권장:

- `(user_id, created_at DESC)`
- `(turn_id)`
- `(model, created_at DESC)`
- `(thread_id, created_at DESC)`

### 3. `tool_execution_events`

dashboard에서 “어떤 유저가 어떤 도구를 얼마나 호출했는지”와 tool latency를 보여주기 위한 fact 테이블.

권장 컬럼:

- `id UUID PK`
- `user_id STRING NOT NULL`
- `thread_id STRING NOT NULL`
- `turn_id UUID NOT NULL`
- `run_id STRING NULL`
- `trace_id STRING NULL`
- `span_id STRING NULL`
- `parent_span_id STRING NULL`
- `node_name STRING NULL`
- `tool_name STRING NOT NULL`
- `display_name STRING NULL`
- `status STRING NOT NULL`
  - `running`, `success`, `error`
- `started_at TIMESTAMPTZ NOT NULL`
- `ended_at TIMESTAMPTZ NULL`
- `duration_ms BIGINT NULL`
- `input_summary JSONB NULL`
- `output_summary JSONB NULL`
- `error_summary JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL`

인덱스 권장:

- `(user_id, started_at DESC)`
- `(turn_id, started_at ASC)`
- `(tool_name, started_at DESC)`

### 4. `trace_events` 확장

현재 raw trace 보존 목적은 유지하되, 최소한 아래 컬럼은 추가하는 것이 좋다.

- `user_id STRING NULL -> NOT NULL로 단계적 승격`
- `turn_id UUID NULL`
- `seq INTEGER NULL`
- `run_id STRING NULL`
- `trace_id STRING NULL`
- `span_id STRING NULL`
- `parent_span_id STRING NULL`

이유:

- 현재 `trace_events`는 `thread_id`만 있어 dashboard query 시 조인/필터 비용이 크다.
- `turn_id + seq`가 있으면 한 turn의 실시간 이벤트 스트림을 안정적으로 재생할 수 있다.

### 5. `llm_pricing_snapshots`

historical cost 안정성을 위한 가격 스냅샷 테이블.

권장 컬럼:

- `id UUID PK`
- `provider STRING NOT NULL`
- `model STRING NOT NULL`
- `pricing_version STRING NOT NULL`
- `effective_from TIMESTAMPTZ NOT NULL`
- `effective_to TIMESTAMPTZ NULL`
- `input_cost_per_1m_microusd BIGINT NOT NULL`
- `output_cost_per_1m_microusd BIGINT NOT NULL`
- `reasoning_cost_per_1m_microusd BIGINT NULL`
- `cache_read_cost_per_1m_microusd BIGINT NULL`
- `notes JSONB NULL`

원칙:

- usage write 시점에 해당 snapshot을 resolve해서 `llm_usage_events`에 cost를 계산해 저장한다.
- 가격이 바뀌어도 historical dashboard가 흔들리지 않는다.

### 6. 선택 사항: `user_daily_usage_rollups`

초기에는 SQL view/materialized view로 충분하지만, 트래픽이 커지면 롤업 테이블도 고려한다.

권장 컬럼:

- `usage_date DATE`
- `user_id STRING`
- `total_turns INTEGER`
- `total_input_tokens BIGINT`
- `total_output_tokens BIGINT`
- `total_reasoning_tokens BIGINT`
- `total_cost_microusd BIGINT`
- `total_reasoning_cost_microusd BIGINT NULL`
- `avg_latency_ms BIGINT`
- `avg_ttft_ms BIGINT`

## Dashboard 관점 추천 쿼리 소스

### 총 토큰

- source: `llm_usage_events`
- 집계:
  - `SUM(total_tokens)` by `user_id`

### 질의 -> 최종 AI 답변 평균 시간

- source: `chat_turns`
- 집계:
  - `AVG(latency_ms)` where `status = 'completed'` and `request_kind in ('chat', 'resume')`

### 총 추론 비용

- source: `llm_usage_events`
- 집계:
  - 우선순위 1: `SUM(reasoning_cost_microusd)` when exact pricing exists
  - 우선순위 2: `SUM(estimated_reasoning_cost_microusd)` when only estimate is available

### 날짜별 토큰 사용량 그래프

- source: `llm_usage_events` 또는 `user_daily_usage_rollups`
- 집계:
  - `DATE(created_at)` 기준 `SUM(input_tokens)`, `SUM(output_tokens)`, `SUM(reasoning_output_tokens)`

### Real-time User Tracing Table

- source: `chat_turns` + latest aggregate from `llm_usage_events`
- 표 컬럼 예시:
  - `timestamp`
  - `user_id`
  - `thread_id`
  - `turn_index`
  - `model`
  - `input_tokens`
  - `output_tokens`
  - `reasoning_tokens`
  - `latency_ms`
  - `ttft_ms`
  - `status`
  - `active_team_final`

## 수집 파이프라인 권장 변경

### 1. `/api/chat`, `/api/chat/resume` 시작 시 `turn_id` 생성

- turn 시작 직후 `chat_turns` row를 `running` 상태로 만든다.
- `turn_index`는 thread별 사용자 질의 turn 기준으로 증가시킨다.
- HITL control message는 별도 `request_kind = 'resume'`로 구분한다.

### 2. LangChain `on_chat_model_end` 계측 추가

- 현재는 `on_chat_model_stream`만 읽고 usage는 추정치로 계산한다.
- 반드시 `on_chat_model_end` 또는 equivalent end event에서 최종 output message의 `usage_metadata`를 읽어 `llm_usage_events`에 저장한다.
- 저장 대상:
  - `input_tokens`
  - `output_tokens`
  - `total_tokens`
  - `input_token_details.cache_read`
  - `output_token_details.reasoning`
  - raw `usage_metadata JSONB`

### 3. tool start/end를 `tool_execution_events`로 정규화

- 현재 SSE + raw trace 생성 로직은 유지한다.
- 추가로 `tool_start`에서 row 생성, `tool_end`/`tool_error`에서 종료 업데이트한다.

### 4. turn 종료 시 `chat_turns` update

- `completed_at`, `latency_ms`, `ttft_ms`, `status`, `response_message_id`, `tool_call_count`를 업데이트한다.
- `first_token_at`은 최초 `text` emission 시점으로 기록한다.

### 5. file logger 역할 축소

- `usage.jsonl`, `session.jsonl`, `user.jsonl`은 개발용 보조 채널로만 남긴다.
- dashboard용 canonical source는 DB fact table로 전환한다.

## 비용 계산 정책

### 정확 비용 vs 추정 비용 분리

- `total_cost_microusd`: pricing snapshot 기준 exact 계산값
- `reasoning_cost_microusd`:
  - reasoning이 별도 과금이면 exact
  - 별도 과금이 아니면 `NULL`
- 필요하면 아래를 별도 컬럼으로 추가:
  - `estimated_reasoning_cost_microusd`

이유:

- reasoning tokens는 usage metadata에 존재해도, 과금 정책이 항상 독립 가격표로 노출되는 건 아니다.
- dashboard에서 `정확 비용`과 `추정 reasoning share`를 섞어 보여주면 지표 신뢰도가 깨진다.

## 마이그레이션 전략

### 권장

- 기존 `trace_events`, `chat_messages`, `chat_sessions`는 유지
- 신규 테이블 추가 + `trace_events` 최소 컬럼 확장
- 과거 데이터는 부분 backfill
- 장기적으로는 analytics sink/warehouse를 붙일 수 있도록 append-friendly schema를 유지

### backfill 우선순위

1. `chat_sessions`, `chat_messages` 기반으로 `chat_turns` 기초 backfill
2. `trace_events.status/checkpoint/text_summary` 기반 latency 대략 backfill
3. 기존 `usage.jsonl`는 추정치이므로 analytics canonical backfill source로는 비권장

## 단계별 구현 체크리스트

## Phase 0. 지표 계약 고정

- [x] `turn`의 정확한 정의를 고정한다.
- [x] `총 추론 비용`을 exact/estimated 중 어떻게 표기할지 정책을 고정한다.
- [x] `usage.jsonl`는 보조 로그이고 DB가 canonical source라는 결정을 고정한다.
- [x] Dashboard 1차 지표 목록을 확정한다.

검증:

- [x] 현재 dashboard 요구와 schema 제안이 1:1 매핑되는지 확인한다.

## Phase 1. DB schema 추가

- [x] `chat_turns` 모델 추가
- [x] `llm_usage_events` 모델 추가
- [x] `tool_execution_events` 모델 추가
- [x] `llm_pricing_snapshots` 모델 추가
- [x] `trace_events` 확장 컬럼 추가 여부 결정 및 반영
- [x] `trace_id` / `span_id` / `parent_span_id` 또는 이에 준하는 식별자 전략을 고정한다.
- [x] startup `create_all` 환경에서 신규 테이블 생성 확인

검증:

- [x] 모델 import / metadata 등록 확인
- [x] startup test 또는 schema smoke test 추가

## Phase 2. Turn lifecycle 계측

- [x] `/api/chat` 시작 시 `chat_turns` row 생성
- [x] `/api/chat/resume` 시작 시 `request_kind = 'resume'`로 row 생성
- [x] 최초 text emission 시 `first_token_at` 기록
- [x] 완료/중단/에러 시 turn 종료 update

검증:

- [x] completed / interrupted / errored turn 각각 pytest로 확인

## Phase 3. Exact usage_metadata 적재

- [x] `on_chat_model_end` 계측 추가
- [x] `usage_metadata` raw JSON 저장
- [x] `reasoning_output_tokens`, `cache_read_input_tokens` 정규화 저장
- [x] `run_id`, `node_name`, `model`과 연결
- [x] `trace/span` 식별자와 usage fact를 연결한다.

검증:

- [x] mocked LangChain end event로 usage_metadata 적재 테스트
- [x] reasoning token breakdown 저장 테스트

## Phase 4. Tool execution 정규화

- [x] tool start row 생성
- [x] tool end / tool error update
- [x] `duration_ms` 계산

검증:

- [x] tool success/error pytest 추가

## Phase 5. Cost snapshot 계산

- [x] pricing snapshot 저장 구조 구현
- [x] usage write 시 cost 계산
- [x] exact vs estimated reasoning cost 정책 구현

검증:

- [x] pricing snapshot lookup test
- [x] cost math test

## Phase 6. Dashboard query 계층

- [ ] user summary query service 추가
- [ ] daily usage series query 추가
- [ ] real-time tracing table query 추가
- [ ] 필요 시 view/materialized view 설계
- [ ] warehouse/OLAP 이전을 염두에 둔 query/view 분리 전략 문서화

검증:

- [ ] aggregate query test
- [ ] date-range test

## Phase 7. Dashboard API

- [ ] `/api/dashboard/summary`
- [ ] `/api/dashboard/daily-usage`
- [ ] `/api/dashboard/live-traces`
- [ ] user authorization 정책 확정

검증:

- [ ] auth/role test
- [ ] response schema test

## Phase 8. Frontend Dashboard

- [ ] `Dashboard` route 추가
- [ ] 총 토큰 카드
- [ ] 평균 latency 카드
- [ ] 총 추론 비용 카드
- [ ] 날짜별 토큰 사용량 그래프
- [ ] 실시간 tracing table

검증:

- [ ] frontend component test
- [ ] Playwright 실브라우저 확인

## 추천 구현 우선순위

1. `chat_turns`
2. `llm_usage_events`
3. `on_chat_model_end usage_metadata` 적재
4. `tool_execution_events`
5. `pricing snapshot`
6. Dashboard API
7. Dashboard UI

## 메모

- 지금처럼 `len(text) // 4` 방식으로는 reasoning-heavy workload를 user별 비용에 반영할 수 없다.
- Dashboard까지 생각하면 raw JSONB만 쌓는 방식은 한계가 분명하다.
- 따라서 이번 작업의 핵심은 `raw trace 유지 + analytics fact table 추가`의 이중 계층 설계다.
