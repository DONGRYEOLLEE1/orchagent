작성일시: 2026-03-24 09:49 KST
최종 수정일시: 2026-03-24 10:20 KST

# Final Response Stream Duplication Refactor Plan

목표: `/api/chat`와 `/api/chat/resume`에서 최종 assistant 응답이 한 turn에 정확히 1회만 사용자에게 스트리밍되고, DB에도 동일한 단일 응답만 저장되도록 스트림 수집 계약과 라우팅 계약을 재정의한다.

## 문제 요약

- 사용자가 웹검색 기반 질의를 보냈을 때 같은 assistant 답변이 3번 반복되어 UI와 DB에 저장되는 치명적 버그가 확인되었다.
- 실제 문제 row를 확인한 결과 `chat_messages.content`에는 동일 답변 블록이 3회 연속 누적되어 있었다.
- 반면 LangGraph 최종 checkpoint state 안의 `assistant` 메시지는 1개만 존재했다.
- 따라서 이 문제는 최종 state 생성 자체의 오류가 아니라, 스트리밍 중간 결과를 최종 응답으로 잘못 누적하는 오류다.

## 확정된 원인

### 1. `head_supervisor`의 speculative final text가 너무 일찍 사용자 채널로 노출된다

- `head_supervisor`는 구조화 출력 LLM 호출에서 `content`를 포함한 응답을 먼저 생성한다.
- 그러나 task plan progression과 finalizer reroute는 그 이후에 적용된다.
- 그 결과 실제 최종 경로가 `writing_team` 또는 `finalizer`로 바뀌더라도, 이미 생성된 `head_supervisor`의 end-user-facing text stream은 취소되지 않고 사용자에게 흘러간다.

관련 코드:

- `packages/agent-core/src/agent_core/supervisor.py`
- LLM 응답 수집: line 234
- plan override: line 327
- finalizer reroute: line 346

### 2. `/api/chat` 스트림 수집기가 여러 run의 text를 모두 같은 최종 응답으로 합친다

- 현재 `apps/backend/api/routes/chat.py`는 `head_supervisor`와 `finalizer`를 모두 최종 텍스트 스트림 노드로 간주한다.
- `on_chat_model_stream`에서 들어오는 text chunk를 run ownership 검증 없이 전부 `final_answer_chunks`에 append한다.
- 따라서 같은 turn 안에서 `head_supervisor` 2회 + `finalizer` 1회가 모두 최종 응답으로 취급되어 그대로 이어붙는다.

관련 코드:

- `apps/backend/api/routes/chat.py`
- `FINAL_TEXT_STREAM_NODES`: line 29
- stream chunk append: line 520
- final answer DB persist: line 704

### 3. 프런트는 백엔드 중복 stream을 그대로 반영한다

- 프런트는 `text` 이벤트를 마지막 assistant bubble에 단순 append한다.
- 따라서 UI의 3회 반복은 프런트 상태 버그가 아니라 백엔드 중복 stream의 직접적인 결과다.

관련 코드:

- `apps/frontend/src/app/page.tsx`: line 754
- `apps/frontend/src/lib/chat-stream.js`: line 41

## 리팩토링 목표

1. 한 turn의 end-user-facing final text owner를 정확히 1개로 제한한다.
2. 경로가 확정되기 전 speculative text는 사용자 채널에 노출하지 않는다.
3. DB 영속화는 canonical final answer 하나만 기준으로 수행한다.
4. `/api/chat`와 `/api/chat/resume`가 동일한 단일 응답 계약을 공유한다.
5. 동일 버그가 재발하면 테스트가 즉시 실패하도록 회귀 케이스를 고정한다.

## 범위

- 포함
  - `apps/backend/api/routes/chat.py`
  - `packages/agent-core/src/agent_core/supervisor.py`
  - `packages/agent-core/src/agent_core/nodes/finalizer.py`
  - 관련 백엔드 테스트 전반
- 제외
  - research/writing prompt 품질 개선
  - UI 디자인 변경
  - thread history 기능 구조 변경

## 전제

- 단순 직접 응답은 `head_supervisor`가 최종 응답 owner가 될 수 있다.
- 팀 위임이 한 번이라도 있었거나, plan 기반 질의이거나, finalizer 경로가 필요한 복합 질의는 `finalizer`가 유일한 최종 응답 owner가 되어야 한다.
- 버그 수정은 프롬프트 의존이 아니라 서버 측 계약으로 강제되어야 한다.

## 수정 원칙

1. “최종 응답은 1회만”이라는 계약을 모델 출력이 아니라 서버 로직으로 강제한다.
2. stream chunk는 즉시 append하지 말고, owner가 확정될 때까지 run 단위로 구분해 관리한다.
3. `head_supervisor`의 응답 텍스트는 route 확정 전에 사용자-visible final answer로 간주하지 않는다.
4. DB persist와 trace summary도 같은 canonical final answer를 기준으로 삼는다.
5. direct answer 경로와 delegated/finalizer 경로를 테스트에서 명시적으로 분리한다.

## 권장 구현 방향

- 권장안 A
  - `chat.py`에서 final text를 즉시 `final_answer_chunks`에 넣지 말고 `run_id`별 buffer로 수집한다.
  - `head_supervisor`의 `on_chain_end` 시점에 실제 route가 `END`인 direct answer일 때만 해당 buffer를 flush한다.
  - route가 `writing_team` 또는 `finalizer`로 바뀌면 `head_supervisor` buffer는 폐기한다.
  - `finalizer` buffer만 canonical final answer로 채택한다.
- 권장안 B
  - `supervisor.py`에서 plan override/finalizer reroute가 필요한 경우 구조화 출력 `content`를 사용자용 텍스트로 사용하지 않는 계약을 더 앞단에서 강제한다.
  - 다만 이 보강은 단독 해결책이 아니라, `chat.py`의 stream collector hardening과 함께 가야 한다.

## 상세 작업 체크리스트

### Phase 0. 재현 시나리오와 실패 조건 고정

- [x] 현재 재현 질의인 `웹검색을 통해 RoPE 알고리즘을 검색하여 500자 내외로 설명해줘.` 를 기준으로 failing regression case를 문서화한다.
- [x] 실패 조건을 “한 turn의 UI assistant bubble에 동일 최종 답변이 2회 이상 반복되면 실패”로 고정한다.
- [x] 실패 조건을 “`chat_messages.content`가 canonical final answer와 다르면 실패”로 고정한다.
- [x] 실패 조건을 “한 turn 안에서 final answer owner run이 2개 이상이면 실패”로 고정한다.
- [x] trace/log 진단 포인트를 `head_supervisor` speculative stream으로 고정한다.
- [x] trace/log 진단 포인트를 `head_supervisor` override 후 reroute로 고정한다.
- [x] trace/log 진단 포인트를 `finalizer` 최종 stream으로 고정한다.

### Phase 1. 단일 최종 응답 계약 설계

- [x] final text owner 판정 규칙을 명시한다.
- [x] `head_supervisor` direct answer 경로를 “팀 위임 없음, finalizer 미사용, 즉시 종료”로 고정한다.
- [x] `finalizer` answer 경로를 “plan 존재 또는 팀 위임 이력 존재 또는 finalizer reroute 발생”으로 고정한다.
- [x] `FINAL_TEXT_STREAM_NODES`의 단순 집합 기반 계약을 owner-aware collector 계약으로 대체할지 결정한다.
- [x] `head_supervisor` text를 즉시 방출하지 않고 buffer 후 승인하는 정책을 채택할지 확정한다.
- [x] canonical final answer source를 확정한다.
- [x] 권장 canonical source를 “selected owner의 flushed stream”으로 사용할지 확정한다.
- [x] fallback canonical source를 “final checkpoint state의 마지막 assistant message”로 사용할지 확정한다.

### Phase 2. `/api/chat` 스트림 수집기 리팩토링

- [x] `final_answer_chunks` 직접 append 구조를 run-aware buffered collector 구조로 변경한다.
- [x] `run_id`, `node`, `route_decision`, `owner_status`, `buffered_text`를 묶어 관리하는 내부 구조를 도입한다.
- [x] `head_supervisor` stream은 `on_chain_end` 전까지 보류하도록 바꾼다.
- [x] `head_supervisor`가 direct terminal answer로 확정된 경우에만 buffer를 사용자에게 flush하도록 바꾼다.
- [x] `head_supervisor`가 `writing_team` 또는 `finalizer`로 reroute된 경우 buffer를 폐기하도록 바꾼다.
- [x] `finalizer` stream은 canonical owner로 채택하고, 같은 turn의 다른 owner 후보를 무효화하도록 바꾼다.
- [x] `direct_messages` fallback이 이미 flush된 owner와 중복 방출하지 않도록 조정한다.
- [x] `fallback_answer = _extract_final_message_from_state(...)` 경로가 앞선 stream flush와 중복되지 않도록 invariant를 세운다.

### Phase 3. `/api/chat/resume` 동일 계약 반영

- [x] `/api/chat`와 `/api/chat/resume`가 같은 stream collector 규칙을 공유하도록 공통화한다.
- [x] resume 경로에서도 `head_supervisor` speculative text가 누적되지 않음을 보장한다.
- [x] resume 경로의 `checkpoint` 복원 이후 direct/finalizer owner 판정이 동일하게 작동하는지 확인한다.

### Phase 4. `head_supervisor` 계약 보강

- [x] `supervisor.py`에서 plan override와 finalizer reroute가 필요한 경우 `content`를 더 이른 시점에 비우거나 무효화할 수 있는지 검토한다.
- [x] 현재처럼 LLM 응답을 받은 뒤에만 override하는 구조가 unavoidable하다면, backend collector가 이를 흡수하도록 명시한다.
- [x] 가능하면 `Command.update`에 direct answer 여부를 명시하는 내부 flag를 추가하는 방안을 검토한다.
- [x] `head_supervisor`의 `Response content:` 로그가 실제로 사용자에게 노출된 텍스트와 1:1 대응하도록 정리한다.

### Phase 5. persistence와 trace summary 정합성 보강

- [x] DB 저장용 `final_answer`는 selected owner의 canonical text만 사용하도록 보장한다.
- [x] `text_summary` trace도 canonical final answer 1개만 남기도록 보장한다.
- [x] final checkpoint state의 마지막 `assistant` message와 DB persisted content가 일치하는지 검증 경로를 만든다.
- [x] owner가 폐기된 speculative text를 debug log로 남길지, 아니면 완전히 무시할지 정책을 확정한다.

### Phase 6. 백엔드 테스트 보강

- [x] `apps/backend/tests/test_api.py`에 direct answer 회귀 테스트를 추가한다.
- [x] 단순 greeting/direct answer는 `head_supervisor` text가 1회만 방출되는지 검증한다.
- [x] plan 기반 질의에서 `head_supervisor`가 intermediate text를 생성해도 최종 응답 채널에는 노출되지 않는지 검증한다.
- [x] `research -> writing -> finalizer` 경로에서 최종 응답이 1회만 방출되는지 검증한다.
- [x] `head_supervisor` 2회 + `finalizer` 1회 상황을 mock으로 재현해도 최종 누적 결과는 1개 답변만 남는지 검증한다.
- [x] persisted `chat_messages.content`가 final checkpoint `assistant` content와 일치하는지 검증한다.
- [x] `text_summary` trace가 1개만 생성되는지 검증한다.
- [x] `/api/chat/resume`에도 동일한 테스트를 추가한다.
- [x] `apps/backend/tests/test_rope_validation.py`를 실제 버그 재현 방어용으로 강화한다.

### Phase 7. Playwright MCP 실브라우저 최종 검증

- [ ] 개발 스택이 정상 구동된 상태에서 Playwright MCP로 실제 프런트 브라우저 세션을 연다.
- [ ] 실제 문제 질의인 `웹검색을 통해 RoPE 알고리즘을 검색하여 500자 내외로 설명해줘.` 를 입력해 스트림 완료까지 기다린다.
- [ ] assistant bubble이 1개이고 동일 답변 블록이 반복되지 않는지 DOM 기준으로 확인한다.
- [ ] thread preview와 중앙 채팅 내용이 같은 답변을 중복 없이 1회만 반영하는지 확인한다.
- [ ] 비슷한 질의인 `웹검색을 통해 ALiBi 위치 인코딩을 조사하고 500자 내외로 설명해줘.` 를 새 thread에서 실행한다.
- [ ] 두 번째 질의에서도 동일한 중복 스트림 현상이 재발하지 않는지 확인한다.
- [ ] 필요 시 Playwright MCP 스냅샷과 스크린샷을 남겨 회귀 증거로 보관한다.
- [ ] 각 브라우저 질의 직후 PostgreSQL에서 최신 `chat_messages` assistant row를 조회해 중복 저장이 사라졌는지 확인한다.
- [ ] 각 브라우저 질의 직후 `trace_events.text_summary`가 1건만 남는지 확인한다.
- [ ] 가능하면 interrupted/resume 시나리오까지 Playwright MCP로 재현해 동일 계약이 유지되는지 확인한다.

## 검증 체크리스트

### 자동 검증 체크리스트

- [x] 관련 `pytest` 타깃을 실행한다.
- [x] direct answer 회귀가 없음을 확인한다.
- [x] delegated/finalizer 회귀가 없음을 확인한다.
- [x] DB persist와 checkpoint state 정합성이 보장되는지 확인한다.
- [x] resume 경로 회귀가 없음을 확인한다.

### 실브라우저 검증 체크리스트

- [ ] Playwright MCP로 실제 브라우저에서 최종 질의 테스트를 수행한다.
- [ ] backend 로그에서 `head_supervisor` speculative text가 최종 응답으로 방출되지 않는지 확인한다.
- [ ] PostgreSQL에서 `chat_messages`, `trace_events`, checkpoint state를 비교해 단일 canonical answer만 남았는지 확인한다.

## 완료 조건

- 사용자-facing assistant 응답이 한 turn당 정확히 1회만 나타난다.
- DB의 `chat_messages.content`가 final checkpoint의 canonical assistant content와 동일하다.
- `head_supervisor` intermediate text와 `finalizer` 최종 text가 섞여 저장되지 않는다.
- `/api/chat`와 `/api/chat/resume` 모두 동일 계약을 만족한다.
- 재현 테스트가 추가되어 같은 유형의 중복 stream 버그가 다시 들어오면 CI에서 즉시 실패한다.
