작성일시: 2026-03-24 10:01 KST
최종 수정일시: 2026-03-24 10:01 KST

# Final Response Stream Ownership Contract

## 목표

- 한 turn의 end-user-facing final answer owner를 정확히 1개로 제한한다.
- speculative intermediate text는 owner가 확정되기 전까지 사용자 채널에 노출하지 않는다.
- DB persist, trace summary, thread preview는 모두 같은 canonical final answer를 기준으로 계산한다.

## 결정 1. Final Text Owner는 set 기반이 아니라 run-aware ownership으로 판정한다

- 기존처럼 `head_supervisor`와 `finalizer`를 모두 final text stream node로 취급하는 방식은 사용하지 않는다.
- 앞으로는 node 집합이 아니라 “이번 turn에서 어떤 run이 최종 응답 owner인가”를 collector가 판정한다.
- 따라서 stream collector는 `run_id`별 buffer와 owner 상태를 관리해야 한다.

## 결정 2. `head_supervisor` direct answer owner 조건

- `head_supervisor`는 다음 조건을 모두 만족할 때만 final answer owner가 된다.
- 팀 위임이 없는 turn이다.
- `finalizer` reroute가 발생하지 않는다.
- `head_supervisor`의 `on_chain_end` 결과가 direct terminal completion이다.
- 사용자에게 방출할 텍스트는 `on_chain_end` 이후 승인된 buffer만 사용한다.

### direct terminal completion 판단 기준

- `goto == END` 또는 동등한 direct 종료 의미를 가진다.
- `streaming_status == "completed"` 이다.
- 현재 turn의 최종 route가 `FINISH`이며 `finalizer`가 아니다.
- 같은 turn 안에 team delegation 이력이 없다.

## 결정 3. `finalizer` owner 조건

- 아래 중 하나라도 만족하면 `finalizer`가 유일한 final answer owner가 된다.
- `task_plan`이 존재하고 `NO_PLAN`이 아니다.
- 같은 turn 안에 team delegation 이력이 있다.
- `head_supervisor`가 `finalizer`로 reroute되었다.

### owner rule

- 이 경우 `head_supervisor`가 생성한 text는 모두 speculative text로 본다.
- speculative `head_supervisor` text는 사용자 채널에 flush하지 않고 폐기 가능해야 한다.
- 최종 사용자 응답은 `finalizer` stream 또는 `finalizer` fallback message만 사용한다.

## 결정 4. `head_supervisor` text는 approval 후 flush한다

- `head_supervisor`의 `on_chat_model_stream` text는 즉시 최종 응답으로 append하지 않는다.
- 해당 text는 `run_id`별 speculative buffer에만 저장한다.
- `on_chain_end`에서 direct terminal answer가 확정된 경우에만 사용자 채널과 persistence 채널로 flush한다.
- `writing_team` 또는 `finalizer`로 route가 바뀌면 해당 buffer는 폐기한다.

## 결정 5. Canonical Final Answer Source

### 1차 canonical source

- selected owner가 승인 후 flush한 stream text를 canonical final answer로 사용한다.

### 2차 fallback source

- selected owner가 stream text를 남기지 못한 경우 final checkpoint state의 마지막 `assistant` message를 fallback canonical source로 사용한다.

### 금지 규칙

- 서로 다른 owner 후보 run의 text를 concat하여 canonical final answer를 만들지 않는다.
- speculative `head_supervisor` text와 `finalizer` text를 섞어서 DB에 저장하지 않는다.
- direct_messages fallback은 이미 승인된 owner stream이 존재할 때 다시 방출하지 않는다.

## 결정 6. Phase 2 구현 방향

- Phase 2에서는 `/api/chat`와 `/api/chat/resume`에 공통으로 쓰이는 owner-aware collector를 도입한다.
- collector는 최소한 다음 상태를 관리해야 한다.
- `run_id`
- `node`
- `buffered_text`
- `owner_candidate`
- `approved_owner`
- `discarded_reason`

## 검증 기준

- 한 turn당 승인된 final answer owner는 정확히 1개여야 한다.
- persisted `chat_messages.content`는 approved owner의 canonical final answer와 일치해야 한다.
- `text_summary` trace는 같은 canonical final answer를 1회만 기록해야 한다.
- thread preview는 canonical final answer의 prefix만 반영해야 한다.
