# Coding Team Head↔Subgraph Ping-Pong Fix Plan

## 배경
`thread_1778113169062`에서 사용자 후속 질의에 대해 coding_team이 코드 답변을 만들고도 head_supervisor와 사이에서 무진전 ping-pong이 20+회 발생, 응답이 ~2분 30초 이상 걸렸다.

```
[Supervisor] Routing decision: coding_team        # head → coding_team
[Supervisor] Routing decision: codebase_explorer  # coding supervisor → 워커 (1회)
[Reviewer - Coding Team] Valid: False, ...
[Supervisor] Routing decision: __end__            # coding supervisor 즉시 종료
[Supervisor] Routing decision: coding_team        # head 다시 coding_team
[Supervisor] Routing decision: __end__            # coding supervisor 워커 호출 없이 즉시 __end__
... 20+회 반복
```

원인:
1. head LLM이 `[Review Failed]` 메시지를 보고 같은 팀으로 매번 재라우팅.
2. coding_team의 워커 도구는 repo 의존(`list_repo_tree`, `apply_patch_edit` 등)이라 thread에 repo가 바인딩되지 않은 단순 코드 출력 요청에선 본질적으로 무의미.
3. `max_team_dispatches=6` 가드는 워커가 실제 dispatch될 때만 카운트되어 head↔subgraph 사이클은 무한 누적되지 않음 → 가드 미작동.
4. reviewer가 단순 코드 예제에도 "runnable 보장"을 요구해 거의 항상 `Valid:False`.

## Phase 1 — 패치 A: head→team 사이클 가드

- [x] `packages/agent-core/src/agent_core/supervisor.py` head 분기에서 task_plan override 안과 밖 두 곳에 `head_redirects_to_team` 카운터 가드 추가. `route_history` 안의 layer="head" + team=target_team 개수가 `HEAD_TEAM_REDIRECT_LIMIT=2` 이상이면 `next_node="FINISH"`. dispatch_count 가드와 별개로 head 재라우팅 횟수 자체를 제한.

## Phase 2 — 패치 B: repo binding 부재 시 coding_team 차단

- [x] `packages/agent-core/src/agent_core/supervisor.py`에 `shared_context.repo_binding`이 falsy이면 head LLM이 `coding_team`으로 라우팅을 골라도 휴리스틱으로 `FINISH`로 우회. task_plan override 안과 밖 양쪽에 가드.
- [x] `packages/prompt-kit/src/prompt_kit/prompts.py` `SYSTEM_SUPERVISOR_PROMPT` 가이드라인 2b 추가: "coding_team은 thread에 repo가 바인딩된 경우에만 사용. 단순 코드 예제·스니펫 출력은 head가 직접 답하거나 finalizer로 보낸다." 가이드라인 12로 "한 번 returning한 팀에 대한 재라우팅 자제" 명시.

## Phase 3 — 패치 C: reviewer 완화

- [x] `REVIEWER_PROMPT`에 "단순 코드 출력 요청에선 runnability 불확실성을 invalid 기준으로 삼지 않는다. 구문·아키텍처가 합리적이면 valid"를 추가. version 1.0 → 1.1.

## Phase 4 — 검증

- [x] backend uvicorn `--reload` + container restart로 새 코드 강제 적용 확인.
- [x] Playwright MCP로 새 thread(`thread_1778117677173`)에 동일 코드 요청 전송. 결과:
  - 응답 시간 51초 (이전 ~2분 30초).
  - 백엔드 로그에서 `[Supervisor] Plan stage coding_team skipped: thread has no bound repository.` 발동 후 `Routing decision: finalizer` → `[Finalizer] Synthesizing final answer...`로 정상 종료.
  - head ↔ coding_team ping-pong 0회.
  - 새 assistant 답변(LangChain `MultiServerMCPClient` + `create_agent` MCP 코드 예제)이 DB에 저장.

## Phase 5 — 정리

- [x] 위 체크박스 모두 `- [x]` 처리.
- [x] `fix(supervisor): break head↔coding_team ping-pong without bound repo` 커밋.
- [x] push.
