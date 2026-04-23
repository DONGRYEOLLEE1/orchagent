---
name: sse-contract
description: "OrchAgent 백엔드 ↔ 프론트엔드 SSE 스트리밍 이벤트 계약의 ground truth. `status/route/reasoning/tool_start/tool_end/tool_error/text/attachments/checkpoint/error` 10종 이벤트의 실제 payload shape, 상태값, FINAL_RESPONSE_STREAM_OWNERSHIP 규칙을 정의한다. SSE 이벤트 추가·수정, 프론트 파서 작성, 백엔드 emit 로직 변경, 경계면 디버깅 시 반드시 이 스킬을 읽는다. 이벤트 shape 합의 없이 양쪽을 각각 수정하지 않는다."
---

# SSE Event Contract — 백↔프론트 스트리밍 계약

실제 구현(`apps/backend/api/routes/chat.py`, `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx::handleStreamEvent`)에서 추출한 ground truth.

## 전송 프레임

백엔드는 모든 이벤트를 SSE `message` 이벤트로 보내고, payload는 **`event_type` 필드를 discriminator로 가진 flat JSON**이다.

```
event: message
data: {"event_type": "status", "status": "running", ...}
```

프론트는 `event_type`으로 분기한다(`WorkspaceRouteRoot.tsx::handleStreamEvent`, L1371-1624).

## 공통 필드

대부분의 이벤트에 등장:
- `event_type: string` — 이벤트 discriminator (필수)
- `node: string | null` — 해당 이벤트를 일으킨 그래프 노드 이름
- `display_name: string` — UI 표시용 사람이 읽는 이름 (`_display_name()` 변환 결과)
- `timestamp: string` — UTC ISO 8601
- `run_id: string | null` — LangGraph run_id (스트리밍 텍스트/툴/추론에서 사용)

## 이벤트 카탈로그

### `status`
턴 라이프사이클 상태. 프론트는 `payload.status === "completed"` 등으로 종료 시점 판정(L1378, L1845, L1990).

```
{
  event_type: "status",
  status: "running" | "completed" | "interrupted" | "errored",
  thread_id: string,
  node: string | null,
  display_name: string,
  active_team: string | null,
  active_worker: string | null,
  message: string,
  timestamp: string
}
```

**상태값 의미**:
- `running` — 턴 진행 중. 초기 emit + 팀 전환 시마다 재발
- `completed` — 턴 정상 종료. 최종 응답 flush 직후
- `interrupted` — HITL `interrupt()` 발생 (`GraphInterrupt` 캐치)
- `errored` — 예외 발생 또는 클라이언트 disconnect 후 회복 실패

빌더: `_status_payload()` (`chat.py:618-633`).

### `route`
Supervisor의 라우팅 결정. `AgentTimeline`에 history로 누적.

```
{
  event_type: "route",
  node: string,
  layer: "head" | "team" | string | null,
  source: string | null,     // 라우팅 출발 노드 (== route_entry.node)
  target: string | null,     // Command(goto=...) 대상 (== route_entry.next)
  team: string | null,
  worker: string | null,
  status: string | null,
  reasoning: string | null,
  display_name: string,
  timestamp: string
}
```

빌더: `_route_payload()` (`chat.py:636-651`). emit 시점: `on_chain_end`에서 `Command.update.route_history` 말단 (`chat.py:1543-1550`).

### `reasoning`
LLM의 reasoning/planning 텍스트 청크.

```
{
  event_type: "reasoning",
  node: string,
  display_name: string,
  content: string,
  run_id: string | null,
  timestamp: string
}
```

emit 시점:
- `on_chat_model_stream`에서 reasoning chunk 추출 성공 시 (`chat.py:1418`)
- Supervisor 라우팅 결정의 `reasoning` 텍스트 (`chat.py:1556`)

### `tool_start`

```
{
  event_type: "tool_start",
  node: string,
  tool_name: string,
  display_name: string,
  input: any,            // _serialize_value(data.get("input"))
  run_id: string | null,
  timestamp: string
}
```

emit 시점: `on_tool_start` (`chat.py:1474`).

### `tool_end`

```
{
  event_type: "tool_end",
  node: string,
  tool_name: string,
  display_name: string,
  output: any,           // _serialize_value(data.get("output"))
  run_id: string | null,
  timestamp: string
}
```

emit 시점: `on_tool_end` (`chat.py:1503`).

### `tool_error`

```
{
  event_type: "tool_error",
  node: string,
  tool_name: string,
  display_name: string,
  error: any,            // _serialize_value(data.get("error"))
  run_id: string | null,
  timestamp: string
}
```

emit 시점: `on_tool_error` (`chat.py:1532`).

### `text`
어시스턴트 텍스트 청크.

```
{
  event_type: "text",
  node: string,          // 보통 "finalizer" 또는 팀 워커 이름, attachments 삽입 시 "assistant"
  display_name: string,
  content: string,
  run_id: string | null, // emission 경로에서 설정됨. 없을 수도 있음
  timestamp: string
}
```

빌더: `_text_payload_from_emission()` (`chat.py:654-662`).

**FINAL_RESPONSE_STREAM_OWNERSHIP** (`chat.py:588-611` `_FinalResponseCollector._approve_chunks`):
- 한 턴에서 `approved_owner_run_id` 게이트가 가장 먼저 승인된 `run_id`만 `text` emit을 허용
- 이후 다른 run_id의 텍스트는 누적만 되고 emit되지 않음
- 최종 응답은 오직 한 경로(보통 finalizer)에서만 스트림됨
- 위반 시 `test_chat_turn_lifecycle.py`, `test_api.py` 등에서 감지

### `attachments`
어시스턴트 메시지에 첨부 파일/이미지 부착.

```
{
  event_type: "attachments",
  role: "assistant",
  message_id: string,
  attachments: Array<{...}>,  // public attachment objects
  timestamp: string
}
```

emit 시점: `chat.py:1682, 2358`. `persist=False` — trace에 남기지 않음.

### `checkpoint`
LangGraph 체크포인트 스냅샷.

```
{
  event_type: "checkpoint",
  thread_id: string,
  node: "checkpoint",
  checkpoint_id: string | null,
  checkpoint_ns: string | null,
  created_at: string | null,
  next_nodes: string[],
  active_team: string | null,
  active_worker: string | null,
  response_mode: string | null,
  streaming_status: string | null,
  message_count: number,
  route_history_length: number,
  timestamp: string
}
```

빌더: `_build_checkpoint_payload()` (`chat.py:665-685`). `next_nodes`가 비어있지 않고 `streaming_status != "completed"`면 사용자 액션 대기 상태(`_checkpoint_requires_user_action`, L688-692).

### `error`
예외 세부 정보(`status: errored` 다음에 별도 emit).

```
{
  event_type: "error",
  node: "OrchAgent",
  message: string,
  timestamp: string
}
```

emit 시점: 예외 블록 (`chat.py:1733, 2401`).

## 프론트 파서 계약

`WorkspaceRouteRoot.tsx::handleStreamEvent` (L1371-1624):

1. `payload.event_type`으로 분기
2. 알려진 10종만 처리 — 미지의 type은 무시(현재 명시적 `console.warn` 없음 — 필요 시 추가 고려)
3. 필수 필드 누락은 해당 이벤트만 버리고 다음 진행
4. `status.status === "completed"`로 턴 종료 확정 (L1845, L1990)
5. `tool_start/end/error`는 같은 `tool_name` 키로 in-flight 맵 관리

## 백엔드 emit 가이드

새 이벤트 타입 또는 필드 추가 시:

1. 이 문서에 shape 먼저 추가
2. `chat.py`의 payload 빌더 함수(또는 인라인 dict)에 반영
3. 프론트 `handleStreamEvent`에 새 분기 추가
4. `qa-verifier`에게 교차 검증 요청 — `integration-qa-protocol` 스킬대로 양쪽 동시 열기

**`_serialize_value()`** 유틸리티가 `input/output/error`의 민감 값 마스킹을 담당 — 새 툴 추가 시 직접 dict 전달 금지.

## resume / 재개 경로

`/api/chat/resume` 엔드포인트도 동일 이벤트 계약을 공유한다 (`chat.py:1960-2490`). 즉 `status: running` → ... → `status: completed | interrupted | errored` 사이에 동일 이벤트 스트림이 흐른다. 차이점:
- resume 턴은 `Command(resume=...)` 페이로드로 시작
- 초기 `status: running` 메시지는 "Resuming..." 문구

## 확장 가이드 (coding 이벤트 등)

새 도메인(coding 등)이 추가 이벤트를 emit해야 할 때 **프론트가 필요한 최소 shape**을 선정하되, 다음 중 하나로 먼저 설계:

- 기존 `checkpoint` 필드에 coding-specific payload를 실어 보내기 (예: `state_values` 내 typed projection)
- 새 `event_type` 도입 (예: `coding_summary_update`) — 이 경우 **양쪽 모두 확장** 후 본 계약서에 추가

**원칙**: 이 문서가 현실과 어긋나면 현실(코드)이 정답. 즉시 이 문서를 갱신한다.

## 관련 참조

- `docs/FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT.md`
- `docs/FINAL_RESPONSE_STREAM_DUPLICATION_INCIDENT.md`
- `plans/FINAL_RESPONSE_STREAM_DUPLICATION_REFACTOR_PLAN.md`
- 백엔드: `apps/backend/api/routes/chat.py` (payload 빌더 L618-685, 초기 턴 스트림 L1329-1810, resume 스트림 L1960-2490)
- 프론트: `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx::handleStreamEvent` (L1371-1624)
- 백엔드 테스트: `test_chat_turn_lifecycle.py`, `test_api.py`, `test_api_disconnect_edge_case.py`, `test_reasoning.py`
- 프론트 테스트: `apps/frontend/src/lib/chat-stream.test.mjs`, `src/lib/workspace-state.test.ts`
