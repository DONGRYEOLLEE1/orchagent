---
작업명: LangGraph Postgres Long-Term Memory Refactor Plan
간단요약: 현재 SQL canonical personal memory를 유지하면서 LangGraph PostgresStore와 조건부 `load_memories` 노드를 추가해 유저별 personalization을 강화하고, retrieval latency 증가를 엄격한 게이트와 캐시/요약 전략으로 제어한다.
작성일시: 2026-03-26 13:41 KST
최종 수정일시: 2026-03-26 15:04 KST
---

# LangGraph Postgres Long-Term Memory Refactor Plan

## 최우선 목표

- 장기기억 메모리를 통해 `유저별 personalization`을 더 자연스럽고 일관되게 강화한다.
- memory가 단순 settings 목록이 아니라 실제 답변 생성 경로에 안정적으로 녹아들게 한다.
- 다만 `load_memories` 도입으로 인한 turn latency/TTFT 악화는 엄격하게 제어한다.

## 문제 정의

현재 구현은 SQL 기반 personal memory를 canonical source로 두고, chat 시작 전에 커스텀 retrieval 결과를 `shared_context.personalization`으로 넣는 구조다.

이 방식은 제품 기능 측면에서는 실용적이지만, 아래 한계가 있다.

- LangGraph/LangChain의 표준 long-term memory store 계층과 분리되어 있다.
- memory retrieval/search namespace 모델이 graph 런타임과 느슨하게 결합돼 있다.
- 향후 semantic search, cross-thread recall, richer memory projection을 키울 때 구조적 확장성이 떨어질 수 있다.
- retrieval policy가 graph node가 아니라 route/service 중심이라, graph 관점에서 memory lifecycle이 덜 명시적이다.

반면 `LangGraph PostgresStore + load_memories`로 바꾸면 이런 장점이 있다.

- LangGraph/LangChain의 공식 long-term memory 모델과 정렬된다.
- namespace/key/document 구조로 user/thread scoped memory를 더 자연스럽게 다룰 수 있다.
- `load_memories`를 graph의 first-class step으로 두어 memory retrieval을 orchestration 흐름에 명시적으로 포함할 수 있다.
- 향후 search/index/semantic retrieval을 표준 경로로 확대하기 쉽다.

하지만 바로 우려되는 리스크도 크다.

- `START -> load_memories -> planner` 구조는 모든 turn에 동기 retrieval latency를 추가한다.
- memory가 적거나 꺼진 사용자에게도 매번 retrieval 비용이 들어갈 수 있다.
- 잘못 설계하면 personalization 품질보다 응답 지연이 더 커질 수 있다.

## 설계 결론

이번 리팩토링의 권장 방향은 `완전 교체`가 아니라 `하이브리드`다.

### 유지할 것

- SQL canonical store
  - `user_memory_entries`
  - `user_memory_settings`
  - `memory_reference_events`
- 이유
  - settings UI
  - soft delete / tombstone
  - KST `created_at`
  - explicit/inferred 구분
  - 운영/감사/정합성 테스트

### 추가할 것

- LangGraph `PostgresStore`
  - retrieval/search 용 projection store
- `load_memories` graph node
  - user/thread 기반 memory를 store에서 읽어 state에 적재

### 바꾸지 않을 것

- memoryAgent의 쓰기 기준 데이터는 SQL canonical을 우선한다.
- store는 canonical이 아니라 `retrieval-optimized projection`으로 취급한다.

즉 구조는 아래와 같다.

1. `memoryAgent`
   - turn 종료 후 candidate 추출
2. SQL canonical upsert
   - settings와 운영 기준 source of truth
3. PostgresStore projection sync
   - agent retrieval 최적화용 복사본
4. `load_memories` node
   - 다음 turn 시작 시 관련 memory를 읽어 graph state에 주입
5. supervisor/finalizer/worker
   - state에 들어온 personalization block을 사용

## 핵심 아키텍처

### 현재

- `/api/chat` route가 retrieval을 직접 호출
- retrieved block을 `shared_context.personalization`에 넣음
- graph는 그 값을 간접적으로만 소비

### 목표

- `START -> load_memories -> planner -> head_supervisor -> teams -> finalizer`
- `load_memories`가 memory retrieval의 단일 공식 진입점이 됨
- route는 thread/user/config만 주입하고 retrieval 자체는 graph가 담당

## LangGraph Store 적용 방식

### 1. Store 초기화

- startup에서 `PostgresStore.from_conn_string(...)`로 store를 초기화한다.
- 현재 `AsyncPostgresSaver`와 같은 PostgreSQL을 써도 되지만, connection/pool/namespace 설계는 분리해서 본다.
- `store.setup()`는 app startup에서 보장한다.

### 2. Namespace 설계

권장 namespace:

- user global memory
  - `("users", user_id, "memory", "global")`
- thread local memory
  - `("users", user_id, "memory", "thread", thread_id)`
- optional summary document
  - 같은 namespace 아래 `summary` key 별도 유지

### 3. Key 설계

- 기본 key는 SQL memory row의 `memory_id`를 그대로 사용한다.
- summary 문서는 고정 key 예:
  - `summary`

### 4. Document payload

store document에는 최소한 아래를 넣는다.

- `memory_id`
- `category`
- `title`
- `content_text`
- `scope_type`
- `source_type`
- `salience`
- `confidence`
- `created_at`
- `updated_at`
- `status`

## load_memories Node 설계

### 위치

- `START -> load_memories -> planner`

이 위치가 맞는 이유:

- planner도 memory를 참고해 plan granularity를 조정할 수 있다.
- supervisor/finalizer 이전에 state에 실어두면 하위 전체 경로가 같은 memory context를 공유할 수 있다.

### 입력

- `user_id`
- `thread_id`
- 최신 user message
- memory settings snapshot

### 출력

- `shared_context.personalization`
- `shared_context.personalization_meta`
  - `memory_ids`
  - `source`
  - `hit_count`
  - `retrieval_ms`

### 수행 순서

1. memory disabled면 즉시 skip
2. user에게 active memory가 없으면 즉시 skip
3. thread local summary 존재 시 우선 로드
4. user global summary 존재 시 보조 로드
5. 필요 시 top-k semantic/exact search 수행
6. compact personalization block 생성
7. `shared_context`에 저장

## Latency 우려와 대응

`load_memories` node는 personalization 품질을 높이는 대신, 동기 경로에 latency를 추가한다. 이건 우연한 부작용이 아니라 명시적으로 관리해야 할 비용이다.

### 우려 포인트

- 모든 turn마다 store access가 발생
- memory row 수가 늘수록 search 비용 증가
- planner 전에 retrieval을 하므로 TTFT에 바로 반영
- resume 경로에서도 같은 비용이 중복될 수 있음

### 대응 원칙

- 항상 retrieval하지 않는다.
- `no memory / disabled / empty namespace`는 초고속 skip한다.
- prompt에 원문 memory 여러 개를 그대로 넣지 않고 `summary + top-k`만 넣는다.
- state에 넣는 block 길이를 엄격히 제한한다.
- retrieval은 `summary-first`, `search-second`로 구성한다.

### 권장 latency 최적화

#### Fast path

- `user_memory_settings.memory_enabled = false`
  - 즉시 skip
- 해당 user active memory count = 0
  - 즉시 skip
- thread local summary만 있으면
  - summary 1건만 읽고 종료

#### Slow path

- summary + recent memory top-k
- top-k는 기본 `최신 메모리 3~5개`로 제한
- initial rollout에서는 semantic search보다 `최신 active memory 우선` 전략을 택한다
- payload char/token cap 적용

#### Summary 전략

- SQL canonical 갱신 시 store에도 `summary` document를 유지
- 대부분의 turn은 summary만 읽고 끝낸다
- summary만으로 부족할 때만 최신 active memory 3~5개를 보조 주입한다

#### Caching 전략

- 동일 `user_id + thread_id` 조합에 대해 최근 retrieval 결과를 짧은 TTL 캐시로 둘지 검토
- 단, memory가 변경되면 캐시 무효화 필요

## MemoryAgent와 Store 동기화

### write path

1. user turn 종료
2. sidecar memoryAgent candidate 생성
3. SQL canonical upsert
4. projection sync worker가 PostgresStore put/update
5. summary regenerate

### sync 정책

- initial rollout에서는 synchronous dual-write보다 `SQL first + async projection sync`가 안전하다.
- projection 실패는 main turn 실패로 전파하지 않는다.
- projection backlog는 observability에 반드시 잡아야 한다.

## 프롬프트/상태 적용 방식

LangGraph store를 붙여도 memory가 자동으로 prompt에 녹아드는 건 아니다. 결국 retrieval 결과를 state나 context에 넣고, supervisor/finalizer/worker가 그 값을 사용하도록 해야 한다.

따라서 다음을 유지한다.

- state에 personalization block을 넣는다.
- prompt helper는 그대로 두되, source가 route retrieval이 아니라 `load_memories` node가 된다.

즉 바뀌는 것은 `어디서 읽느냐`이지, `아예 프롬프트 주입이 필요 없어진다`가 아니다.

## 단계별 계획

## Phase 0. ADR 및 기준 고정

- [x] SQL canonical + PostgresStore projection의 이중 구조를 공식 결정한다.
- [x] PostgresStore는 canonical이 아니라 retrieval projection이라는 점을 문서에 고정한다.
- [x] `load_memories` node를 graph 진입점에 두는 방향을 확정한다.
- [x] latency concern을 release blocker로 취급하는 원칙을 고정한다.
- [x] personalization 우선, 단 p95 gate 준수라는 목표를 문서에 고정한다.

## Phase 1. Store 인프라 추가

- [x] `langgraph.store.postgres.PostgresStore` 의존성과 초기화 경로를 점검한다.
- [x] startup에서 store setup을 수행한다.
- [x] store connection lifecycle을 정리한다.
- [x] store helper/service를 추가한다.
- [x] namespace/key schema를 코드 상수로 정리한다.

## Phase 2. SQL -> Store Projection

- [x] `user_memory_entries`를 store document로 projection하는 service를 만든다.
- [x] create/update/delete 시 projection sync 규칙을 만든다.
- [x] deleted/tombstone memory의 store projection 처리 방식을 정한다.
- [x] summary document 생성/갱신 정책을 추가한다.
- [x] projection failure logging/trace를 추가한다.

## Phase 3. load_memories Node 구현

- [x] `packages/agent-core` 또는 backend workflow 쪽에 `load_memories` node를 추가한다.
- [x] state schema에 personalization meta를 확장한다.
- [x] `START -> load_memories -> planner`로 graph를 재구성한다.
- [x] `load_memories`가 memory disabled / empty memory에서 즉시 skip하도록 구현한다.
- [x] retrieval latency를 state/trace에 기록한다.
- [x] resume 경로에서도 동일 retrieval 규칙을 적용할지 정한다.

## Phase 4. Prompt/Context 통합 재정리

- [x] route-layer retrieval 코드를 제거하거나 fallback 용도로만 축소한다.
- [x] supervisor/finalizer/prompt helper가 node-produced personalization block만 사용하도록 정리한다.
- [x] block size cap, top-k cap, summary-first 규칙을 코드로 고정한다.
- [x] memory reference event 기록을 node 기준으로 재정리한다.

## Phase 5. Latency Hardening

- [x] fast path skip 구현
- [x] active memory count short-circuit 구현
- [x] summary-only retrieval 우선 구현
- [x] search fallback 조건을 최소화
- [x] retrieval cache 도입 여부 검토
- [x] prompt injection 길이 cap을 적용

## Phase 6. Migration 및 Backfill

- [x] 기존 `user_memory_entries`를 store로 backfill하는 스크립트를 만든다.
- [x] per-user summary document를 생성한다.
- [x] backfill idempotency를 보장한다.
- [x] rollout 전후 count/sample validation을 추가한다.

## Phase 7. Observability 및 Evaluation

- [x] `load_memories` latency trace event 추가
- [x] retrieval hit/miss metrics 추가
- [x] store sync failure metric 추가
- [x] memory reference와 final answer correlation 확인 경로 추가
- [ ] personalization quality evaluation fixture 추가

## 성능 검증 계획

### 필수 지표

- p50/p95 TTFT
- p50/p95 total latency
- `load_memories` node latency
- summary-only path latency
- summary+search path latency
- prompt injection token 증가량
- projection sync backlog

### 필수 비교 축

- memory off baseline
- SQL-only 현재 구현
- SQL canonical + PostgresStore + load_memories

### release gate

- `load_memories` 도입 후 p95 TTFT가 baseline 대비 10% 초과 악화 시 실패
- p95 total latency가 baseline 대비 15% 초과 악화 시 실패
- summary-only path p95가 80ms 초과면 경고, 120ms 초과면 실패
- summary+search path p95가 180ms 초과면 경고, 250ms 초과면 실패

## 정합성 통합 테스트

- [ ] 선호도 신호 있는 질의는 store projection까지 완료되는지 검증한다.
- [ ] 선호도 신호 없는 질의는 `load_memories`가 기존 memory만 읽고 새 memory write는 만들지 않는지 검증한다.
- [x] 동일 user의 다른 thread에서도 user global memory가 자연스럽게 recall되는지 검증한다.
- [x] cross-thread recall 시나리오를 고정한다.
  - 1번 스레드: `난 가수 백예린을 좋아해. 대표곡 5개만 뽑아줘.`
  - memory 저장: `사용자는 가수 백예린을 좋아한다.`
  - 2번 스레드: `내가 좋아하는 가수는 누구게?`
  - 기대 응답: `사용자님은 가수 백예린을 좋아하십니다.`에 준하는 personalization 반영
- [ ] thread local memory는 같은 thread에서만 우선 recall되는지 검증한다.
- [x] memory delete 후 store projection과 SQL canonical이 함께 반영되는지 검증한다.
- [x] summary document가 SQL canonical과 불일치하지 않는지 검증한다.

## 수동 검증 시나리오

- [x] user A의 1번 스레드에서 `난 가수 백예린을 좋아해. 대표곡 5개만 뽑아줘.` 질의를 보내 memory 저장
- [x] 같은 user의 2번 스레드에서 `내가 좋아하는 가수는 누구게?` 질의를 보내 cross-thread recall을 확인
- [x] 선호 신호 없는 질의에서는 추가 memory가 생기지 않는지 확인
- [x] settings personal memory 목록과 실제 retrieved behavior가 일치하는지 확인
- [x] memory delete 후 후속 thread에서 해당 personalization이 약화/제거되는지 확인

## 완료 조건

- LangGraph `PostgresStore`가 retrieval projection 계층으로 안정적으로 동작한다.
- `load_memories` node가 graph 초기 단계에서 personalization context를 제공한다.
- settings/UI의 canonical memory와 graph retrieval memory가 논리적으로 일치한다.
- personalization 품질은 개선되지만 latency gate는 넘지 않는다.
- user별, thread별 장기기억이 실제 답변에 더 자연스럽게 반영된다.
