# Stale Fallback on Interrupt Fix Plan

## 배경
`thread_1778113169062`("LangGraph MCP 에이전트")에서 사용자가 langchain/langgraph/mcp 통합 코드를 요청한 이후, 어떤 새 user 메시지를 보내도 직전 turn의 assistant 답변이 **글자 단위로 동일**하게 5초 이내에 다시 출력되는 현상이 재현되었다.

근본 원인:
1. head_supervisor가 코드 출력 요청을 `requires_approval=true`로 분류 → `interrupt()` → 그래프가 head_supervisor에서 멈춤.
2. `apps/backend/api/routes/chat.py`의 SSE 종료 처리부에서 `collector.collect_state_fallback(state_values)`이 무조건 호출되어, 체크포인터에 저장된 `state.messages` 끝의 **이전 turn AIMessage**를 fallback final answer로 stream + DB(`chat_messages`)에 저장.
3. 결과: HITL interrupt 상태에서 stale answer 누출.

근거 라인:
- `apps/backend/api/routes/chat.py:1638-1742` (POST `/chat` 흐름)
- `apps/backend/api/routes/chat.py:2329-2440` (POST `/chat/resume` 흐름)
- `apps/backend/api/routes/chat.py:582-594` (`collector.collect_state_fallback`)
- `packages/agent-core/src/agent_core/supervisor.py:499-506` (`interrupt()` 호출)
- `packages/prompt-kit/src/prompt_kit/prompts.py:30` (코드 실행 = approval 정책 광의 해석)

## Phase 1 — 백엔드 fallback 누출 차단 (옵션 A)

- [x] `apps/backend/api/routes/chat.py` POST `/chat` 흐름(1638~1742)에서 `_checkpoint_requires_user_action(checkpoint_payload)` 결과를 한 번 계산하여 변수로 보관, True면:
  - `collector.collect_state_fallback(state_values)` 호출 skip
  - 그 이후 `final_answer` DB 저장 분기 skip
- [x] POST `/chat/resume` 흐름(2329~2440)에 동일 패치 적용.
- [x] 흐름 변경이 정상 turn(non-interrupt) 케이스의 final answer 저장에 영향 없는지 코드상 확인.

## Phase 2 — supervisor approval 정책 명확화 (옵션 C)

- [x] `packages/prompt-kit/src/prompt_kit/prompts.py`의 `SYSTEM_SUPERVISOR_PROMPT` 가이드라인 11번을 다음 두 가지로 분리:
  - 11. 실제로 **shell/python을 실행하거나, 파일을 생성/변경/삭제하거나, 외부 부수효과(네트워크 mutation, DB write 등)를 발생시키는 작업**에 한해 `requires_approval=true`로 설정.
  - 11a. **단순히 코드 스니펫·예제·설명을 텍스트로 출력하는 것은 'executing code'가 아니다.** 사용자에게 코드를 보여주는 것만 요청한 경우 `requires_approval=false`.
- [x] `version` 문자열 갱신 (2.3 → 2.4).

## Phase 3 — 검증

- [x] backend uvicorn `--reload`로 자동 적용 확인 (logs: `StatReload detected changes in 'api/routes/chat.py'` / `'/app/packages/prompt-kit/src/prompt_kit/prompts.py'` 양쪽 reload 완료).
- [x] Playwright MCP로 `thread_1778113169062` 진입 → 동일 질의("아니 그냥 간단한 코드만 출력해주면 돼. langchain+langgraph+mcp 를 통한 agent")를 다시 보냄 → 다음을 확인:
  - 응답 시간이 5초 이상으로 늘어남 (LLM 신규 호출 발생): **약 2분 28초** (09:55:09 → 09:57:37).
  - 응답 텍스트가 직전 turn과 다른 새 답변: **확인** — 새 응답은 ` ```python ` 블록 (`pip install langchain langchain-openai langgraph...`)으로 시작하는 실 LangChain+LangGraph+MCP 코드 예제.
  - 백엔드 로그에 `[Finalizer] Synthesizing final answer...` 진입(또는 적어도 `[Supervisor] Routing decision: ` 가 finalizer/팀으로 이어짐): **`[Supervisor] Routing decision: coding_team`** 정상 라우팅, 더 이상 `Interrupting for user approval` 없음.
- [x] DB `chat_messages`에서 새 assistant message가 직전과 다른 content로 저장됐는지 확인 (12 → 14 row, 신규 assistant content는 코드 블록).
- [x] interrupt가 여전히 발생하는 경우(real-mutation 의도)에도 stale answer가 출력되지 않고 "Requires user action." 상태로만 마무리되는지 확인 (코드 path: `requires_user_action=True`면 `collect_state_fallback` 및 DB persist 모두 skip하도록 가드 적용 — 회귀 없음).

## Phase 4 — 정리

- [x] 위 체크박스 모두 `- [x]` 처리.
- [ ] `fix(chat): suppress stale state fallback on HITL interrupt` 단일 커밋 (또는 phase별 분할).
- [ ] push.
