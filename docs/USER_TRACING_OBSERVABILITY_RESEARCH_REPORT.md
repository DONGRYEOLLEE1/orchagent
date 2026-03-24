작성일시: 2026-03-24 17:08 KST

# User Tracing Observability Research Report

## 요약

LLM/agent observability 제품들은 대체로 같은 패턴으로 수렴한다.

- 실행 단위는 `trace -> span/run/observation` 계층으로 나눈다.
- multi-turn 관계는 `thread` 또는 `session`으로 별도 연결한다.
- user-level analytics를 위해 `user_id`, `session_id`, `trace_id`를 모든 telemetry에 전파한다.
- dashboard 지표는 raw JSON event에서 직접 계산하지 않고, token/cost/latency용 정규화 fact 또는 OLAP table에서 집계한다.
- 비용 계산은 실제 token metadata와 pricing table/snapshot을 결합해서 계산한다.
- reasoning/cache/token breakdown은 “있으면 저장”이 아니라, 처음부터 first-class 컬럼으로 다루는 제품이 강하다.

이 조사 결과는 현재 `orchagent` 계획에서 제안한 `chat_turns`, `llm_usage_events`, `tool_execution_events`, `pricing snapshots` 방향이 업계 사례와 잘 맞는다는 점을 뒷받침한다. 다만 장기적으로는 `Postgres canonical + analytics sink/warehouse`까지 고려하는 것이 더 안전하다.

## 조사 범위

- OpenAI Agents SDK tracing
- LangSmith observability concepts
- Langfuse tracing / self-hosted architecture
- Helicone analytics / query model
- Arize Phoenix tracing / cost tracking / metrics

## 사례별 조사

## 1. OpenAI Agents SDK

### 확인된 사실

- OpenAI Agents SDK는 agent run 동안 `LLM generations`, `tool calls`, `handoffs`, `guardrails`, `custom events`를 built-in tracing 대상으로 둔다.
- 기본 모델은 `trace`와 `span` 계층으로 설명된다.
- 여러 `run()`을 하나의 상위 trace로 묶기 위해 `withTrace()`를 제공한다.
- trace export는 batch processor + exporter 구조를 가진다.

### 시사점

- OpenAI는 thread/message 테이블보다 먼저 `trace/span` 실행 모델을 기준축으로 잡는다.
- 즉, user dashboard를 만들 때도 “대화”와 “실행”을 분리하는 것이 자연스럽다.
- `orchagent`에서도 `thread_id`만으로는 부족하고, `turn_id`, `trace_id`, `run_id` 계층이 필요하다.

### schema 관점 해석

공개 문서에는 OpenAI 내부 DB schema가 없다. 다만 공식 개념 모델은 아래와 같이 해석할 수 있다.

- `Trace`
  - end-to-end workflow
  - conversation/thread와는 별도 개념
- `Span`
  - generation/tool/handoff/guardrail 같은 하위 작업
- `group_id`
  - 여러 trace를 같은 conversation으로 묶는 연결 키

즉, 내부 schema가 공개되어 있지 않더라도 설계 방향은 `thread/session`과 `trace/span` 이중축이다.

출처:
- [OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-js/guides/tracing/)

## 2. LangSmith

### 확인된 사실

- LangSmith는 주요 primitive를 `Project`, `Trace`, `Run`, `Thread`, `Feedback`, `Tags`, `Metadata`로 설명한다.
- `Run`은 단일 작업 단위이고, OpenTelemetry의 span과 유사하게 설명된다.
- `Trace`는 여러 run의 집합이다.
- `Thread`는 multi-turn conversation을 표현한다.
- `Metadata`와 `Tags`는 필터/그룹화/분석을 위한 first-class 개념이다.
- trace 본문은 삭제돼도 historic usage/cost 같은 제한된 metadata는 통계를 위해 유지한다고 명시한다.

### 시사점

- 대시보드용 analytics에서는 raw trace body와 summary metadata를 분리 저장하는 전략이 중요하다.
- `orchagent`도 long retention이 필요한 값은 raw payload JSON이 아니라 normalized fact로 유지해야 한다.
- feedback/annotation 계층은 현재 요구 범위 밖이지만, 장기적으로 dashboard/eval 확장을 고려하면 염두에 둘 가치가 있다.

### schema 관점 해석

LangSmith 공개 문서는 물리 schema를 공개하지 않지만, 논리 schema는 분명하다.

- `trace`
  - root request
- `run`
  - child step
- `thread`
  - conversation grouping
- `metadata/tags`
  - slice-and-dice 차원
- `feedback`
  - eval/annotation 차원

`orchagent` 계획에 그대로 대응시키면:

- `chat_turns` ~= trace-level summary fact
- `trace_events` / 향후 span-level facts ~= run/step data
- `chat_sessions` ~= thread
- `metadata`는 JSONB로 시작하되, dashboard 집계용 차원 컬럼은 별도 승격

출처:
- [LangSmith Observability Concepts](https://docs.langchain.com/langsmith/observability-concepts)

## 3. Langfuse

### 확인된 사실

- Langfuse Python API/SDK 문서에서는 `traces`, `observations`, `scores`를 주요 단위로 다룬다.
- SDK는 `user_id`, `session_id`, `trace_name`, `metadata`, `tags`를 모든 span/observation에 전파하는 사용 패턴을 제공한다.
- self-hosted 배포 문서는 기본 데이터 스토어로 `PostgreSQL`, `ClickHouse`, `Redis`를 언급한다.
- 상태 페이지에서도 `traces`, `observations`, `scores` 조회 성능 문제가 `ClickHouse`와 연관돼 나타난다.

### 시사점

- Langfuse는 OLTP와 analytics를 분리한 구조를 전제로 한다고 보는 것이 합리적이다.
- 즉, tracing을 장기적으로 dashboard에 잘 쓰려면 `Postgres만으로 끝낸다`가 아니라 `warehouse-ready`하게 설계해야 한다.
- user/session propagation을 SDK 레벨에서 강제하는 점도 중요하다. `orchagent` 역시 tracing write 시 `user_id`, `thread_id`, `turn_id`를 항상 넣는 방향이 맞다.

### schema 관점 해석

공개 문서상 물리 schema는 직접 드러나지 않지만, 아래 논리 구조가 강하게 드러난다.

- `trace`
  - user/session에 연결되는 root entity
- `observation`
  - span-like child entity
- `score`
  - trace/observation에 붙는 평가 결과
- storage split
  - metadata/transactional state: Postgres
  - high-volume trace analytics: ClickHouse

이는 `orchagent`에 다음 함의를 준다.

- 처음부터 모든 걸 JSONB 한 테이블에 넣는 건 장기적으로 취약하다.
- raw trace와 analytics fact를 분리해야 한다.
- 나중에 `ClickHouse`나 DWH로 넘길 수 있게 key를 명시적으로 저장해야 한다.

출처:
- [Langfuse Python API Reference](https://python.reference.langfuse.com/langfuse)
- [Langfuse Self-hosting (PostgreSQL, ClickHouse, Redis)](https://langfuse.com/self-hosting/deployment/kubernetes-helm)
- [Langfuse status incident mentioning traces, observations, scores and ClickHouse](https://status.langfuse.com/incident/476987)

## 4. Helicone

### 확인된 사실

- Helicone은 request analytics를 SQL로 직접 조회하는 `HQL`을 제공한다.
- 문서에 공개된 주요 analytics columns:
  - `request_created_at`
  - `request_model`
  - `status`
  - `user_id`
  - `cost`
  - `prompt_tokens`, `completion_tokens`, `total_tokens`
  - `properties`
- 예시 SQL은 `request_response_rmt` 테이블을 직접 대상으로 한다.
- `Helicone-User-Id`, `Helicone-Session-Id`, `Helicone-Session-Path` 헤더를 통해 user/session/parent-child trace 개념을 전달한다.
- cost 값은 `ClickHouse`에서 정수 스케일로 저장된다고 명시한다.

### 시사점

- dashboard/analytics에 최적화된 넓은 denormalized fact table 패턴이 실제로 유효하다.
- 실시간 user tracing 테이블을 그릴 때 필요한 칼럼 집합도 거의 공개되어 있다.
- `properties` 같은 custom dimension map은 유용하지만, 핵심 집계 축(`user_id`, `session_id`, `model`, `status`, `tokens`, `cost`)은 반드시 top-level 컬럼이어야 한다.

### schema 관점 해석

Helicone의 공개 query model은 다음에 가깝다.

- 1 row = 1 LLM request/response fact
- 이 row에 user, session, model, status, tokens, cost, custom properties를 평평하게 담는다
- interactive dashboard는 raw event join보다 이 테이블 직접 조회를 선호한다

이는 `orchagent`에 두 가지 선택지를 준다.

1. normalized facts (`chat_turns`, `llm_usage_events`, `tool_execution_events`) 유지
2. 별도 rollup/view에서 Helicone-style wide analytics table 제공

초기 단계에서는 1이 더 안전하고, dashboard API나 view에서 2를 파생하는 것이 좋다.

출처:
- [Helicone HQL](https://docs.helicone.ai/features/hql)
- [Helicone Header Directory](https://docs.helicone.ai/helicone-headers/header-directory)

## 5. Arize Phoenix

### 확인된 사실

- Phoenix는 tracing을 `trace`와 `span` 계층으로 본다.
- cost tracking은 token counts + model pricing data 조합으로 자동 계산한다고 설명한다.
- OpenInference semantic conventions를 기준으로 required/optional token attributes를 명시한다.
- optional detailed token breakdown에 `prompt_details.cache_read`, `completion_details.reasoning` 같은 항목이 포함된다.
- project metrics dashboard에는
  - trace latency/errors
  - cost over time by token type
  - top models by cost
  - token usage by token type
  - tool calls and errors
  가 포함된다.

### 시사점

- `reasoning_output_tokens`, `cache_read_input_tokens`를 컬럼으로 승격하는 현재 계획 방향은 Phoenix와 강하게 합치한다.
- 비용 계산도 별도 pricing table/snapshot을 둬야 한다는 점이 분명하다.
- dashboard가 요구하는 대부분의 지표는 결국 `trace/turn fact + usage fact + pricing metadata` 조합으로 나온다.

### schema 관점 해석

Phoenix는 OpenTelemetry/OpenInference semantic conventions 중심이라, 물리 schema보다 span attribute model이 중요하다.

`orchagent`에 번역하면:

- `chat_turns`
  - trace-level request summary
- `llm_usage_events`
  - span-level LLM usage fact
- `tool_execution_events`
  - span-level tool fact
- `llm_pricing_snapshots`
  - cost math source

즉 Phoenix는 우리의 정규화 fact 설계를 가장 직접적으로 지지하는 사례다.

출처:
- [Phoenix Cost Tracking](https://arize.com/docs/phoenix/tracing/how-to-tracing/cost-tracking)
- [Phoenix Metrics Dashboard](https://arize.com/docs/phoenix/tracing/llm-traces/metrics)
- [Phoenix Tracing Concepts](https://arize.com/docs/phoenix/learn/tracing)

## 종합 결론

## 공통 패턴

사례를 종합하면 공통 패턴은 다음과 같다.

1. `trace/span` 계층은 거의 필수다.
2. multi-turn grouping은 `thread` 또는 `session`으로 별도 둔다.
3. `user_id`는 raw metadata가 아니라 top-level dimension으로 가져간다.
4. 비용은 정확 token metadata + pricing table에서 계산한다.
5. dashboard는 raw JSON event를 직접 긁지 않고, 정규화 fact나 OLAP table을 사용한다.
6. long-term scale를 고려하면 OLTP와 analytics 저장소 분리가 강한 패턴이다.

## `orchagent`에 대한 권장 해석

### 지금 바로 해야 할 것

- `chat_turns` 도입
- `llm_usage_events` 도입
- `usage_metadata` exact 적재
- `reasoning_output_tokens` / `cache_read_input_tokens` 정규화
- `tool_execution_events` 도입
- `pricing snapshots` 도입

### 설계에 추가로 넣어야 할 것

- `trace_id`, `run_id`, `seq`, `session/thread grouping`을 analytics-friendly하게 저장
- raw trace와 dashboard fact 분리
- 장기적으로는 `ClickHouse`나 DWH로 넘길 수 있게 이벤트 키를 명시적으로 보존

### 과도하게 서두를 필요 없는 것

- 처음부터 ClickHouse를 바로 넣는 것
- dataset/eval/feedback까지 한 번에 확장하는 것

처음엔 `Postgres canonical facts + aggregate query layer`로 시작하고, scale 문제가 생기면 `analytics sink`를 붙이는 쪽이 현실적이다.

## 계획서 반영 포인트

이 조사 결과를 기준으로 tracing schema 계획에는 아래를 반영하는 것이 적절하다.

- `chat_turns`는 trace-level fact로 고정
- `llm_usage_events`는 exact `usage_metadata` 저장을 전제로 설계
- `reasoning cost`는 exact/estimated 구분 정책을 명시
- `trace_events`에는 `turn_id`, `run_id`, `seq`, `user_id` 확장 권장
- long-term note로 `warehouse/ClickHouse-ready` 구조를 추가
- dashboard API는 raw trace 조회가 아니라 fact aggregation 중심으로 설계

## 참고 링크

- [OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-js/guides/tracing/)
- [LangSmith Observability Concepts](https://docs.langchain.com/langsmith/observability-concepts)
- [Langfuse Python API Reference](https://python.reference.langfuse.com/langfuse)
- [Langfuse Self-hosting (Kubernetes Helm)](https://langfuse.com/self-hosting/deployment/kubernetes-helm)
- [Langfuse status incident (ClickHouse / traces, observations, scores)](https://status.langfuse.com/incident/476987)
- [Helicone HQL](https://docs.helicone.ai/features/hql)
- [Helicone Header Directory](https://docs.helicone.ai/helicone-headers/header-directory)
- [Phoenix Cost Tracking](https://arize.com/docs/phoenix/tracing/how-to-tracing/cost-tracking)
- [Phoenix Metrics Dashboard](https://arize.com/docs/phoenix/tracing/llm-traces/metrics)
- [Phoenix Tracing Concepts](https://arize.com/docs/phoenix/learn/tracing)
