# Phase 1-1: 네이티브 서브그래프 통합 계획 (Native Subgraph Integration)

## 1. 목표 (Objective)
현재 진행 중인 네이티브 서브그래프 전환을 `main_graph` 수준에서 끝내지 않고, 팀 내부 워커 실행 경로와 스트리밍 이벤트 계약까지 포함한 end-to-end 구조로 완성합니다. 최종 목표는 다음 4가지입니다.

- `main_graph -> team subgraph -> worker/agent` 전 구간에서 **토큰 단위 실시간 스트리밍**이 끊기지 않을 것
- 팀 경계를 넘어 **상태(State), 툴 실행 메타데이터, 체크포인트**가 일관되게 유지될 것
- 프런트엔드가 LangGraph raw event에 직접 의존하지 않고 **안정적인 SSE 계약** 위에서 동작할 것
- 향후 HITL, validator loop, artifact handoff를 넣어도 구조를 다시 뜯어고치지 않아도 될 것

## 2. 현재 코드베이스 기준선 (Observed Baseline)
코드 리뷰 기준 현재 상태는 다음과 같습니다.

- **완료:** `apps/backend/workflow/main_graph.py`에서 각 팀 서브그래프를 `builder.add_node("research_team", research_graph)` 형태로 직접 연결했습니다.
- **완료:** 각 팀 실행 종료 후 `head_supervisor`로 복귀하는 엣지를 명시적으로 추가했습니다.
- **완료:** `apps/backend/api/routes/chat.py`에서 `graph.astream_events(..., version="v2")`를 사용해 SSE 스트리밍을 전달하고 있습니다.
- **미완:** 팀 내부 워커 노드(`apps/backend/workflow/teams/*.py`)는 여전히 `create_agent(...).invoke(state)`를 래퍼 함수 안에서 동기 호출하고 있습니다.
- **미완:** 워커 결과를 `HumanMessage(content=result["messages"][-1].content, name=...)`로 평탄화하여, 원래의 `AIMessage`, `ToolMessage`, tool call 메타데이터, reasoning 메타데이터를 유실하고 있습니다.
- **미완:** `packages/agent-core/src/agent_core/state.py`의 `BaseAgentState`는 사실상 `messages`와 `next`만 보유하므로 팀 간 구조화된 산출물 전달이 어렵습니다.
- **미완:** 프런트엔드(`apps/frontend/src/app/page.tsx`)는 `on_chat_model_stream`의 raw payload 문자열을 재파싱하고 있으며, 로딩 종료도 특정 이벤트 이름에 의존하고 있어 이벤트 스키마가 조금만 바뀌어도 깨질 수 있습니다.
- **미완:** `TraceService.create_event()`는 스트림 이벤트마다 DB commit을 수행하므로, 토큰/툴 이벤트가 많아질수록 지연과 DB 부하가 커질 수 있습니다.

## 3. 핵심 판단 (What Phase 1-1 Must Actually Finish)
현재 상태는 엄밀히 말해 **"Head Graph에 Native Subgraph를 연결한 1차 마이그레이션"** 까지만 완료된 상태입니다. 실제로 Phase 1-1이 끝났다고 말하려면 아래 항목까지 포함되어야 합니다.

1. **팀 내부 워커도 네이티브 Runnable/Graph로 노출**되어 worker-level stream event가 상위까지 전달될 것
2. **메시지 타입과 툴 메타데이터를 보존**한 채 상위 상태로 병합될 것
3. **백엔드 SSE 이벤트를 정규화**하여 프런트가 brittle parsing 없이 동작할 것
4. **체크포인터, trace, resume**가 서브그래프 내부 단계까지 검증될 것

## 4. 구현 단계 (Implementation Steps)

- **[x] 단계 1: `main_graph.py` 래퍼 함수 제거 및 직접 연결**
  - 기존의 `call_research_team`, `call_paper_writing_team` 등의 래퍼 함수를 제거했습니다.
  - 컴파일된 서브그래프(`research_graph`, `writing_graph`, `vision_graph`)를 `main_graph`의 노드로 직접 추가했습니다.

- **[x] 단계 2: 서브그래프 종료 후 상위 그래프로 복귀하는 엣지 설정**
  - `research_team -> head_supervisor`
  - `writing_team -> head_supervisor`
  - `vision_team -> head_supervisor`
  - 이로써 팀 단위 라우팅은 LangGraph 네이티브 방식으로 동작합니다.

- **[x] 단계 3: 상태(State) 스키마 확장 및 병합 규칙 명문화**
  - `BaseAgentState`에 아래 구조화 필드를 추가하는 방안을 검토합니다.
  - `shared_context`: 팀 간 전달할 요약 사실, 조사 결과, 중간 판단
  - `artifacts`: 문서 초안, 차트 경로, 스크래핑 결과 등 산출물 핸들
  - `route_history`: head/team/worker 라우팅 이력
  - `active_team`, `active_worker`: UI와 trace에서 현재 실행 주체를 안정적으로 표시하기 위한 필드
  - `streaming_status`: `running`, `completed`, `errored` 같은 상위 실행 상태
  - 메시지 병합 규칙은 `MessagesState` 기본 reducer에 기대되, 구조화 필드는 overwrite인지 append인지 명시적으로 정의합니다.
  - 구현 반영:
  - `packages/agent-core/src/agent_core/state.py`에 `shared_context`, `artifacts`, `route_history`, `active_team`, `active_worker`, `streaming_status` 필드와 reducer를 추가했습니다.
  - `shared_context`, `artifacts`: 재귀 dict merge
  - `route_history`: append reducer
  - `active_team`, `active_worker`, `streaming_status`: 마지막 업데이트 overwrite
  - `packages/agent-core/src/agent_core/supervisor.py`에서 head/team supervisor가 route metadata와 active execution metadata를 함께 기록하도록 업데이트했습니다.

- **[x] 단계 4: 팀 내부 워커 래퍼 제거 및 worker-level native composition 적용**
  - 현재 `research.py`, `writing.py`, `vision.py`의 워커 노드는 `agent.invoke(state)` 호출을 감싸고 있습니다.
  - 이 레이어를 제거하거나 최소화해서 `create_agent(...)`가 생성한 runnable/graph를 네이티브 노드로 직접 연결하는 구조를 우선 검토합니다.
  - 부득이하게 래퍼가 필요하다면 최소한 아래는 보존되어야 합니다.
  - `AIMessage` / `ToolMessage` 타입
  - tool call metadata
  - reasoning metadata
  - worker identity (`team`, `worker`, `node_name`)
  - 목표는 "팀은 네이티브 서브그래프인데 워커는 다시 블로킹 래퍼"인 현 상태를 제거하는 것입니다.
  - 구현 반영:
  - `packages/agent-core/src/agent_core/builder.py`에 `add_worker()`를 추가해 worker를 `create_react_agent(..., state_schema=BaseAgentState, version="v2")` 기반 네이티브 서브그래프로 등록하도록 변경했습니다.
  - `apps/backend/workflow/teams/research.py`, `writing.py`, `vision.py`에서 `agent.invoke(state)` 래퍼와 `HumanMessage` 평탄화를 제거했습니다.
  - 각 worker는 팀 서브그래프 내부에서 `worker -> supervisor` 엣지로 복귀하며, 메시지/툴 메타데이터는 worker graph가 생성한 원형 그대로 유지됩니다.

- **[x] 단계 5: SSE 이벤트 계약 표준화 및 프런트엔드 의존성 분리**
  - `chat.py`에서 LangGraph raw event를 그대로 흘리는 대신, UI 친화적인 이벤트 계약으로 정규화합니다.
  - 권장 이벤트 타입:
  - `status`: graph started / team switched / completed / errored
  - `text`: 최종 답변 토큰
  - `reasoning`: reasoning summary 토큰
  - `tool_start`, `tool_end`, `tool_error`
  - `route`: `head_supervisor -> research_team -> search` 같은 전환 이벤트
  - `checkpoint`: resume 가능한 스냅샷 또는 checkpoint id 정보
  - 프런트는 `on_chat_model_stream` raw 문자열을 다시 JSON처럼 파싱하지 않고, 위 계약만 소비하도록 변경합니다.
  - 로딩 종료는 `on_chain_end`의 특정 노드명 비교가 아니라 명시적 `status=completed` 이벤트 기준으로 처리합니다.
  - 구현 반영:
  - `apps/backend/api/routes/chat.py`에서 raw LangGraph event를 `status`, `route`, `text`, `reasoning`, `tool_start`, `tool_end`, `tool_error`, `checkpoint`, `error` 계약으로 정규화합니다.
  - raw `on_chat_model_stream` 문자열 재파싱은 제거하고, direct supervisor 응답도 동일한 `text` 계약으로 통일합니다.

- **[x] 단계 6: 체크포인터/트레이스 운영 경로 고도화**
  - `thread_id` 기준으로 team/worker 내부 단계까지 checkpoint가 실제 저장되는지 검증합니다.
  - resume 또는 time-travel 테스트 시, 서브그래프 내부 노드에서 재개 가능한지 확인합니다.
  - trace는 현재 이벤트마다 commit하므로 다음 중 하나를 검토합니다.
  - turn 단위 batch insert
  - 중요 이벤트만 영속화하고 raw token stream은 샘플링 또는 축약 저장
  - 긴 base64/image/tool payload에 대한 추가 truncation 규칙
  - 요청마다 그래프를 재컴파일하는 현재 구조는 유지 비용이 있으므로, lifespan에서 graph factory/cache를 관리할지 검토합니다.
  - 구현 반영:
  - `TraceService.create_events()`를 추가해 trace를 turn 단위 batch insert로 저장합니다.
  - `text`/`reasoning`은 token별 raw insert 대신 요약 이벤트로 집계 저장하고, base64/장문 문자열은 축약합니다.
  - 스트림 완료 후 `graph.aget_state(..., subgraphs=True)` 기반 `checkpoint` 이벤트를 송신합니다.
  - 동일 `thread_id` 재호출 시 checkpoint가 갱신되고 state가 이어지는 resume 테스트를 추가했습니다.

- **[x] 단계 7: 테스트 범위 확장**
  - 현재 테스트는 주로 그래프 컴파일 성공, 기본 SSE 응답, supervisor 라우팅 검증에 머물러 있습니다.
  - Phase 1-1 완료 기준 테스트는 아래를 포함해야 합니다.
  - 팀 간 메시지 병합 후 상위 상태에서 최신 메시지와 구조화 필드가 모두 보존되는지
  - worker-level `on_chat_model_stream` / `on_tool_start` / `on_tool_end` 이벤트가 SSE로 전달되는지
  - supervisor 직접 응답과 team 위임 응답이 동일한 프런트 계약으로 표시되는지
  - checkpoint 생성 후 동일 `thread_id`로 resume 했을 때 route/state가 이어지는지
  - 에러 발생 시 `status=errored`와 적절한 사용자 메시지가 함께 전달되는지
  - 프런트에서 "Coordinating team..." 로딩 UI가 정상 해제되는지
  - 구현 반영:
  - `apps/backend/tests/test_api.py`에서 normalized SSE 계약, direct supervisor 응답 계약, checkpoint/resume 동작을 검증합니다.
  - `apps/backend/tests/test_error_handling.py`에서 `status=errored` + `error` 이벤트 계약을 검증합니다.
  - `apps/backend/tests/test_trace_service.py`에서 trace batch insert와 truncation 규칙을 검증합니다.

## 5. 세부 고도화 제안 (Feature Uplift Beyond the Original Plan)
단순 마이그레이션을 넘어서, 아래 항목을 이번 문서에 함께 묶어두는 것이 향후 재작업을 줄입니다.

### 5.1 Shared Artifact Handoff
- Research Team의 조사 결과를 단순 텍스트 메시지로만 넘기지 말고 `shared_context.research_findings` 같은 구조화 필드로 전달
- Writing Team은 해당 구조화 결과를 입력으로 받아 초안 생성
- Vision Team은 이미지 분석 결과를 `artifacts` 또는 `shared_context.vision`으로 저장
- 이렇게 해야 이후 validator, citation, export 기능을 붙이기 쉬워집니다.

### 5.2 Routing Transparency
- `route_history`에 head/team/worker 전환을 누적 기록
- trace DB와 UI 타임라인 모두 같은 source of truth를 사용
- 향후 "왜 Research Team이 호출되었는가"를 설명할 수 있도록 supervisor rationale 요약도 선택적으로 저장

### 5.3 Supervisor and Worker Naming Discipline
- 현재 이벤트 노드명은 `head_supervisor`, `research_team`, `search`, `web_scraper` 등이 혼재합니다.
- UI/trace/analytics 용도로 아래 메타데이터를 함께 강제하는 것이 좋습니다.
- `layer`: `head`, `team`, `worker`, `tool`
- `team`: `research`, `writing`, `vision`
- `worker`: `search`, `doc_writer`, `vision_analyst` 등
- `display_name`: 프런트에서 그대로 보여줄 사람이 읽을 수 있는 이름

### 5.4 Streaming UX Safety
- reasoning과 final answer 토큰을 서로 다른 채널로 유지
- assistant message 시작/종료 이벤트를 별도 도입하여 프런트가 메시지 버블 lifecycle을 안정적으로 관리
- tool output은 raw dump 대신 truncate + structured preview 정책 적용

## 6. 검증 시나리오 (Validation Matrix)

### 시나리오 A: Research Team 스트리밍
- 입력: 최신 국제 이슈 질의
- 기대 결과:
- `head_supervisor -> research_team -> search/web_scraper` 라우팅 확인
- worker-level 토큰 스트리밍이 SSE에 노출
- 최종 답변 완료 후 `status=completed` 수신
- 프런트 로딩 UI 해제

### 시나리오 B: Supervisor 직접 응답
- 입력: 단순 인사 또는 상식 질문
- 기대 결과:
- 팀 위임 없이 `head_supervisor`가 직접 응답
- 프런트는 동일한 `text` 이벤트 계약으로 렌더링
- 로딩 종료 규칙이 노드명에 의존하지 않음

### 시나리오 C: Vision Team 멀티모달 처리
- 입력: 텍스트 + 이미지
- 기대 결과:
- `vision_team`으로 라우팅
- 이미지 메타데이터/리사이즈 도구 호출이 tool event로 노출
- base64 원문은 trace 저장 시 축약

### 시나리오 D: Resume / Time-Travel
- 입력: 동일 `thread_id`로 여러 턴 수행
- 기대 결과:
- 이전 state와 checkpoint가 복원
- 서브그래프 내부 단계까지 추적 가능
- route history와 artifacts가 유지

## 7. 완료 기준 (Definition of Done)
아래 조건을 모두 만족해야 Phase 1-1을 완료로 간주합니다.

- `main_graph` 뿐 아니라 팀 내부 워커 실행도 네이티브 composition 또는 동등한 event-preserving 방식으로 전환됨
- worker-level 스트리밍과 tool event가 상위 SSE까지 손실 없이 전달됨
- 메시지/상태 병합 규칙이 문서와 코드에 모두 반영됨
- 프런트가 raw LangGraph event 문자열 파싱 없이 정규화된 SSE 계약만 사용함
- checkpoint/resume이 서브그래프 내부까지 검증됨
- 로딩 인디케이터, trace 저장, 에러 처리에 대한 회귀 테스트가 추가됨

## 8. 기대 효과 (Expected Impact)
- **TTFT 및 체감 응답성 개선:** 팀 내부 워커 토큰이 바로 화면에 도달
- **관측성 향상:** supervisor, team, worker, tool 단위 trace가 일관된 구조로 축적
- **상태 보존력 강화:** message-only 구조를 넘어 artifact/context 중심 협업 가능
- **프런트 안정성 향상:** brittle event parsing 제거로 UI 회귀 감소
- **다음 단계 준비 완료:** validator loop, HITL, citation, export 기능을 무리 없이 얹을 수 있는 기반 확보
