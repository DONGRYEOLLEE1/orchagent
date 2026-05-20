---
작업명: Supervisor Intent Routing Schema Plan
간단요약: 현재 supervisor 라우팅 구조, route_history/SSE 계약, 프론트 소비 경로를 기준으로 team supervisor intent 필드를 추가하고 정규식 기반 coding/research/data_science override를 단계적으로 이관한다.
작성일시: 2026-04-23 22:10 KST
최종 수정일시: 2026-05-19 22:34 KST
---

# Supervisor Intent Routing Schema Plan

## 목표

- Team supervisor가 `next`와 함께 optional `intent`를 structured output으로 반환하게 한다. 현재 `Router`는 `reasoning`, `next`, `content`, `requires_approval`만 선언하고 `llm.with_structured_output(Router).ainvoke(...)` 결과를 사용한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:385-391`, `packages/agent-core/src/agent_core/supervisor.py:462-468`)
- `intent`를 route timeline과 SSE `route` 이벤트까지 흘려보내서 백엔드 로그, trace, 프론트 디버그가 같은 routing contract를 보게 한다. 현재 `RouteEntry`와 `build_route_entry()`에는 `intent`가 없고, `_route_payload()`도 `intent`를 emit하지 않는다. (근거: `packages/agent-core/src/agent_core/state.py:12-20`, `packages/agent-core/src/agent_core/state.py:63-82`, `apps/backend/api/routes/chat.py:653-668`)
- Coding team부터 PoC를 진행한 뒤 research, data_science로 확장한다. 현재 세 팀은 각각 전용 supervisor prompt와 deterministic override가 있으나 intent 분류 지침은 없다. (근거: `packages/prompt-kit/src/prompt_kit/prompts.py:56-112`, `packages/agent-core/src/agent_core/supervisor.py:647-770`)

## 비목표

- Head supervisor의 팀 선택 휴리스틱을 이번 계획에서 제거하지 않는다. 현재 head는 repo binding, 첨부 파일, 이미지에 따라 coding/data_science/vision team을 강제한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:771-842`)
- HITL 승인 정규식은 이번 plan의 1차 대상이 아니다. 현재 `_APPROVAL_PATTERNS`와 `requires_human_approval_for_text()`가 approval interrupt를 보호한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:19-32`, `packages/agent-core/src/agent_core/supervisor.py:477-507`)
- Writing/vision team은 이번 rollout에서 제외한다. 두 팀은 공통 team supervisor prompt를 쓰거나 단일 worker 경로를 쓰며, 이 plan이 겨냥하는 deterministic intent override가 없다. (근거: `apps/backend/workflow/teams/writing.py:36-42`, `apps/backend/workflow/teams/vision.py:15-18`, `packages/agent-core/src/agent_core/supervisor.py:647-770`)
- `langgraph.prebuilt.create_react_agent` 도입은 금지다. 워커 생성은 현재 `langchain.agents.create_agent`를 사용한다. (근거: `packages/agent-core/src/agent_core/builder.py:39-46`, `.claude/skills/langgraph-graph-patterns/SKILL.md:10-18`)

## 현재 아키텍처 요약

- 루트는 `uv` workspace이고 backend, agent-core, agent-tools, prompt-kit 네 패키지를 workspace member로 둔다. (근거: `pyproject.toml:8-14`)
- 백엔드는 FastAPI 앱에서 chat/dashboard/auth/threads/users/memory/repositories/uploads/health 라우터를 `/api` prefix로 등록한다. (근거: `apps/backend/main.py:80-104`)
- LangGraph 최상위 graph는 `load_memories -> planner -> head_supervisor` 흐름을 만들고 research/writing/vision/data_science/coding subgraph를 노드로 등록한 뒤 각 team을 다시 head supervisor로 연결한다. (근거: `apps/backend/workflow/main_graph.py:19-83`)
- LLM 초기화는 `init_chat_model(..., reasoning={"summary": "auto"})`로 한 곳에서 수행된다. (근거: `apps/backend/workflow/main_graph.py:19-25`)
- TeamBuilder는 supervisor, optional reviewer, worker subgraph를 등록하고 worker 완료 후 reviewer 또는 supervisor로 되돌린다. (근거: `packages/agent-core/src/agent_core/builder.py:48-81`)
- Worker agent는 `create_agent(model=self.llm, tools=..., system_prompt=..., state_schema=BaseAgentState, name=...)`로 생성된다. (근거: `packages/agent-core/src/agent_core/builder.py:30-46`)
- `BaseAgentState`는 `shared_context`, `artifacts`, `route_history`, active team/worker, streaming status, response mode를 가진다. `shared_context`는 recursive merge라서 turn-scoped flag를 명시적으로 reset하지 않으면 이전 값이 남을 수 있다. (근거: `packages/agent-core/src/agent_core/state.py:22-35`, `packages/agent-core/src/agent_core/state.py:85-96`)
- `/api/chat`와 `/api/chat/resume`은 graph `astream_events(..., version="v2")`를 SSE로 정규화하고, `Command.update.route_history`의 마지막 entry를 `route` 이벤트로 emit한다. (근거: `apps/backend/api/routes/chat.py:1568-1588`, `apps/backend/api/routes/chat.py:2248-2288`)
- 프론트는 `requestStream('/api/chat')`와 `requestStream('/api/chat/resume')`로 SSE stream을 받고, `WorkspaceRouteRoot.handleStreamEvent()`가 `event_type`으로 분기한다. (근거: `apps/frontend/src/lib/api.ts:504-516`, `apps/frontend/src/lib/api.ts:582-592`, `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx:1410-1485`)

## 실제 코드와 기존 계획의 차이

- 기존 계획의 `Router` line reference는 stale이다. 현재 `Router`는 `supervisor_node()` 내부 `TypedDict`이고 `intent`가 없다. (근거: `packages/agent-core/src/agent_core/supervisor.py:385-391`)
- 기존 계획의 `TypedDict, total=False` 확장안은 모든 기존 필드를 optional로 만들 수 있어 부정확하다. `next`는 현재 `response["next"]`로 필수 접근되고, 나머지는 `.get()` fallback으로 처리된다. (근거: `packages/agent-core/src/agent_core/supervisor.py:462-480`)
- 기존 계획의 "기존 36 케이스" 검증 표현은 확인되지 않는다. 현재 별도 coding supervisor 테스트 파일은 3개 테스트만 담고 있으며, broader supervisor 테스트는 여러 team override를 함께 검증한다. (근거: `apps/backend/tests/test_coding_supervisor.py:20-108`, `apps/backend/tests/test_supervisor.py:388-520`, `apps/backend/tests/test_supervisor.py:891-993`)
- `intent`를 `shared_context`에 저장하려면 current-turn reset이 먼저 필요하다. 현재 `/api/chat` input은 `vision_routed_for_current_turn`만 false로 초기화하고, supervisor는 `coding_routed_for_current_turn`/`data_science_routed_for_current_turn`도 읽고 true로 기록한다. (근거: `apps/backend/api/routes/chat.py:1302-1322`, `packages/agent-core/src/agent_core/supervisor.py:771-800`, `packages/agent-core/src/agent_core/supervisor.py:941-951`)
- SSE 계약 문서에는 `route.reasoning`까지 정의되어 있지만 `intent`는 없다. 새 필드 추가 시 계약 문서, backend payload builder, frontend handler를 같이 갱신해야 한다. (근거: `.claude/skills/sse-contract/SKILL.md:57-76`, `.claude/skills/sse-contract/SKILL.md:229-237`, `apps/frontend/src/types/agent.ts:58-69`)
- 프론트 route consumer는 현재 `display_name`/`target`만 timeline에 반영한다. `intent`를 UI에 보일지 raw trace에만 둘지 결정해야 한다. (근거: `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx:1476-1485`, `apps/frontend/src/components/sidebar/AgentTimeline.tsx:3-13`, `apps/frontend/src/components/sidebar/AgentTimeline.tsx:60-89`)

## 데이터 계약

### Router structured output

`Router`는 기존 필드를 유지하고 `intent`만 optional로 추가한다. 전체 `TypedDict`를 `total=False`로 바꾸지 않는다. 현재 `next`는 필수 인덱싱이고 `reasoning/content/requires_approval`은 fallback 접근이므로, optional 추가는 `NotRequired[str | None]` 또는 동등한 필드별 optional 문법으로 한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:387-391`, `packages/agent-core/src/agent_core/supervisor.py:462-480`)

```python
class Router(TypedDict):
    reasoning: str
    next: str
    content: str
    requires_approval: bool
    intent: NotRequired[str | None]
```

### RouteEntry / SSE route

`intent`는 `RouteEntry`에 optional field로 추가하고 `build_route_entry(..., intent=...)`를 통해 route history에 남긴다. `_route_payload()`는 `route_entry.get("intent")`를 그대로 optional field로 emit한다. (근거: `packages/agent-core/src/agent_core/state.py:12-20`, `packages/agent-core/src/agent_core/state.py:63-82`, `apps/backend/api/routes/chat.py:653-668`)

### Team별 soft intent 값

| Team | 값 | 적용 대상 | 근거 |
| :--- | :--- | :--- | :--- |
| coding | `read_only`, `edit`, `verify`, `unknown` | edit/runtime 여부 판단 | `_CODING_EDIT_INTENT_PATTERNS`, `_RUNTIME_VERIFY_PATTERNS`, coding override가 edit/runtime boolean을 계산한다. (`packages/agent-core/src/agent_core/supervisor.py:56-76`, `packages/agent-core/src/agent_core/supervisor.py:703-770`) |
| research | `search`, `scrape`, `finalize`, `unknown` | search 우선, review failed 후 scraper, scrape 후 finish | research override가 dispatched worker와 review pass/fail로 search/web_scraper/FINISH를 강제한다. (`packages/agent-core/src/agent_core/supervisor.py:673-701`) |
| data_science | `profile`, `analyze`, `visualize`, `finalize`, `unknown` | data_engineer/data_analyst/FINISH 단계 | data science override가 data_engineer 우선, data_analyst 후 review/chart evidence로 FINISH를 결정한다. (`packages/agent-core/src/agent_core/supervisor.py:647-672`) |

## Phase 0. 계약 정리 및 turn-scoped 상태 안전장치

- [ ] `RouteEntry`에 optional `intent`를 추가하고 `build_route_entry()` 인자도 optional로 확장한다. 기존 `reasoning`처럼 값이 있을 때만 entry에 넣는다. (근거: `packages/agent-core/src/agent_core/state.py:12-20`, `packages/agent-core/src/agent_core/state.py:63-82`)
- [ ] `shared_context`에 intent cache를 둘 경우, `/api/chat` 시작 input에서 `coding_intent_for_current_turn`, `research_intent_for_current_turn`, `data_science_intent_for_current_turn`, `coding_routed_for_current_turn`, `data_science_routed_for_current_turn`를 명시적으로 reset하는 작업을 포함한다. 현재 merge reducer는 누락 key를 보존한다. (근거: `packages/agent-core/src/agent_core/state.py:22-35`, `apps/backend/api/routes/chat.py:1302-1322`, `packages/agent-core/src/agent_core/supervisor.py:771-800`, `packages/agent-core/src/agent_core/supervisor.py:941-951`)
- [ ] `/api/chat/resume`에서는 resume command가 기존 interrupted state를 이어받으므로, resume 경로에 새 intent reset을 무조건 넣지 말고 resume semantics를 별도 테스트로 고정한다. (근거: `apps/backend/api/routes/chat.py:1915-2028`, `.claude/skills/sse-contract/SKILL.md:240-245`)
- [ ] state 변경 영향 범위를 plan에 명시한 뒤 구현한다. `.claude` graph 규약은 state 변경을 breaking change로 본다. (근거: `.claude/skills/langgraph-graph-patterns/SKILL.md:37-45`, `.claude/agents/graph-architect.md:52-56`)

검증:
- [ ] `uv run pytest tests/test_state_schema.py -v`로 route history reducer와 새 optional field 보존을 확인한다. (근거: `apps/backend/tests/test_state_schema.py:35-43`)
- [ ] `uv run pytest tests/test_api_resume_edge_cases.py tests/test_api.py -v`로 resume/state 이벤트 회귀를 확인한다. (근거: `apps/backend/api/routes/chat.py:1915-2028`, `.claude/skills/sse-contract/SKILL.md:240-245`)

## Phase 1. Router schema와 route/SSE contract 확장

- [ ] `Router`에 `intent: NotRequired[str | None]`를 추가하고 `response.get("intent")`를 normalize하는 helper를 둔다. `TypedDict, total=False` 전체 전환은 하지 않는다. (근거: `packages/agent-core/src/agent_core/supervisor.py:385-391`, `packages/agent-core/src/agent_core/supervisor.py:462-480`)
- [ ] head/team 공통 supervisor update에서 `build_route_entry(..., intent=router_intent)`를 넘긴다. head route와 team route 모두 같은 route history shape을 유지한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:917-932`, `packages/agent-core/src/agent_core/supervisor.py:953-969`)
- [ ] `_route_payload()`에 optional `intent` 필드를 추가하고 `/api/chat`와 `/api/chat/resume`의 두 emit 경로가 동일 payload builder를 쓰는지 확인한다. (근거: `apps/backend/api/routes/chat.py:653-668`, `apps/backend/api/routes/chat.py:1568-1588`, `apps/backend/api/routes/chat.py:2265-2288`)
- [ ] `.claude/skills/sse-contract/SKILL.md`의 `route` payload shape에 `intent: string | null` optional을 추가한다. 새 SSE 필드는 contract 먼저 갱신해야 한다. (근거: `.claude/skills/sse-contract/SKILL.md:57-76`, `.claude/skills/sse-contract/SKILL.md:229-237`)
- [ ] `apps/frontend/src/types/agent.ts`의 `StreamRouteEvent`에 `intent?: string | null`을 추가한다. (근거: `apps/frontend/src/types/agent.ts:58-69`)
- [ ] `WorkspaceRouteRoot.handleStreamEvent()`는 `intent`를 필수 UI dependency로 삼지 않고 raw traces에는 보존되게 둔다. 현재 route branch는 timeline 표시만 업데이트한다. (근거: `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx:1415-1416`, `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx:1476-1485`)

검증:
- [ ] `uv run pytest tests/test_api.py tests/test_chat_turn_lifecycle.py -v`로 route event 순서와 final response ownership을 확인한다. (근거: `apps/backend/tests/test_api.py:237-249`, `docs/FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT.md:80-85`)
- [ ] `cd apps/frontend && npm run test -- src/app/page.test.tsx`로 stream event union 변경이 UI 테스트를 깨지 않는지 확인한다. (근거: `apps/frontend/src/app/page.test.tsx:1450-1490`, `apps/frontend/src/app/page.test.tsx:1570-1590`)

## Phase 2. Coding team intent PoC

- [ ] `CODING_TEAM_SUPERVISOR_PROMPT`에 `intent` 값을 반드시 선택하라는 지침과 `read_only/edit/verify/unknown` 판단 기준을 추가한다. 프롬프트는 prompt-kit에서만 수정한다. (근거: `packages/prompt-kit/src/prompt_kit/prompts.py:95-112`, `.claude/agents/tool-prompt-specialist.md:19-24`)
- [ ] coding override에서 `edit_requested`와 `runtime_requested`를 `router_intent` 우선으로 계산하고, intent가 없거나 `unknown`이면 기존 regex helper로 fallback한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:56-76`, `packages/agent-core/src/agent_core/supervisor.py:273-285`, `packages/agent-core/src/agent_core/supervisor.py:703-770`)
- [ ] `verify` intent가 단독으로 들어와도 edit 후 runtime verification인지, read-only runtime inspection인지 정책을 고정한다. 현재 runtime verifier는 implementation engineer 이후, review passed 이후에만 호출된다. (근거: `packages/agent-core/src/agent_core/supervisor.py:745-754`, `apps/backend/workflow/teams/coding.py:45-55`)
- [ ] `intent`를 route history와 backend log에 남긴다. 현재 supervisor는 routing decision/reasoning/content만 print한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:892-901`, `packages/agent-core/src/agent_core/supervisor.py:923-969`)
- [ ] coding read-only 흐름을 명시 테스트한다. 현재 별도 coding test에는 read-only explorer 후 FINISH 케이스가 없다. (근거: `apps/backend/tests/test_coding_supervisor.py:20-108`, `packages/agent-core/src/agent_core/supervisor.py:719-728`)
- [ ] coding intent mock 테스트는 `intent=read_only`, `intent=edit`, `intent=verify`, `intent=None`, `intent=unknown`을 포함한다. 기존 fake LLM들은 `next`만 반환하는 경우가 있으므로 missing intent compatibility를 유지해야 한다. (근거: `apps/backend/tests/test_supervisor.py:8-20`, `packages/agent-core/src/agent_core/supervisor.py:462-480`)

검증:
- [ ] `uv run pytest tests/test_coding_supervisor.py tests/test_supervisor.py tests/test_team_subgraphs.py -v`를 실행한다. (근거: `apps/backend/tests/test_coding_supervisor.py:20-108`, `apps/backend/tests/test_team_subgraphs.py:86-108`, `apps/backend/tests/test_team_subgraphs.py:187-192`)
- [ ] 수동: repo binding 후 "이 레포 구조만 설명해줘"가 `intent=read_only`, explorer 후 FINISH로 끝나는지 확인한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:719-728`, `apps/backend/workflow/teams/coding.py:23-67`)
- [ ] 수동: repo binding 후 "README 첫 줄 바꿔줘"가 `intent=edit`, explorer -> implementation_engineer로 진행하는지 확인한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:729-744`)
- [ ] 수동: "UI 수정하고 화면까지 확인해줘"가 `intent=verify`, implementation review passed 후 runtime_verifier로 이어지는지 확인한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:745-754`, `apps/backend/tests/test_coding_supervisor.py:71-108`)

## Phase 3. Research team intent 확장

- [ ] `RESEARCH_TEAM_SUPERVISOR_PROMPT`에 `search/scrape/finalize/unknown` intent 지침을 추가한다. 현재 prompt는 search-first, scraper-after-search 순서만 규정한다. (근거: `packages/prompt-kit/src/prompt_kit/prompts.py:56-74`)
- [ ] research override는 `intent`를 참고하되, 첫 dispatch는 여전히 `search`를 강제하고, `scrape` intent는 search가 이미 dispatch된 뒤에만 허용한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:673-689`)
- [ ] review pass/fail 종료 guard는 유지한다. 현재 scraper 이후 pass/fail 모두 FINISH로 loop를 막는다. (근거: `packages/agent-core/src/agent_core/supervisor.py:690-701`)
- [ ] research prompt policy 테스트에 intent 지침과 기존 search->scrape ordering 문구가 함께 유지되는지 추가한다. (근거: `apps/backend/tests/test_team_subgraphs.py:187-192`, `apps/backend/tests/test_research_prompt_policy.py:30-31`)

검증:
- [ ] `uv run pytest tests/test_supervisor.py::test_research_team_supervisor_starts_with_search tests/test_supervisor.py::test_research_team_supervisor_escalates_to_scraper_after_failed_search_review tests/test_supervisor.py::test_research_team_supervisor_finishes_after_failed_scrape_review_to_avoid_loops -v`를 실행한다. (근거: `apps/backend/tests/test_supervisor.py:891-993`)
- [ ] `uv run pytest tests/test_team_subgraphs.py tests/test_research_prompt_policy.py -v`를 실행한다. (근거: `apps/backend/tests/test_team_subgraphs.py:187-192`, `apps/backend/tests/test_research_prompt_policy.py:30-31`)

## Phase 4. Data science team intent 확장

- [ ] `DATA_SCIENCE_TEAM_SUPERVISOR_PROMPT`에 `profile/analyze/visualize/finalize/unknown` intent 지침을 추가한다. 현재 prompt는 data_engineer 후 data_analyst 순서를 규정한다. (근거: `packages/prompt-kit/src/prompt_kit/prompts.py:76-93`)
- [ ] data_science override는 `intent`를 참고하되, 첫 dispatch는 `data_engineer`를 유지하고, 분석/시각화 intent는 data_engineer 이후 `data_analyst`로 연결한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:647-658`)
- [ ] `finalize` intent가 와도 review passed 또는 chart artifact evidence guard 없이 성급히 FINISH하지 않도록 한다. 현재 FINISH 조건은 review passed 또는 visualization 요청 + chart evidence다. (근거: `packages/agent-core/src/agent_core/supervisor.py:659-672`)
- [ ] file attachment 기반 head routing과 team intent는 분리한다. head는 첨부/질문 패턴으로 data_science_team을 강제할 수 있다. (근거: `packages/agent-core/src/agent_core/supervisor.py:34-43`, `packages/agent-core/src/agent_core/supervisor.py:246-256`, `packages/agent-core/src/agent_core/supervisor.py:793-812`)

검증:
- [ ] `uv run pytest tests/test_supervisor.py::test_data_science_team_supervisor_starts_with_data_engineer tests/test_supervisor.py::test_data_science_team_supervisor_forces_data_analyst_after_engineer tests/test_supervisor.py::test_data_science_team_supervisor_finishes_when_chart_artifact_evidence_exists tests/test_supervisor.py::test_data_science_team_supervisor_finishes_after_review_passed_without_chart -v`를 실행한다. (근거: `apps/backend/tests/test_supervisor.py:388-520`)
- [ ] CSV/XLSX attachment 수동 시나리오에서 data_engineer -> data_analyst -> FINISH 순서를 확인한다. (근거: `docs/DATA_SCIENCE_ANALYTICS_TEAM_RESEARCH.md:323-348`, `apps/backend/workflow/teams/data_science.py:17-51`)

## Phase 5. Regex fallback 축소 및 cleanup

- [ ] Coding team에서 intent 누락률과 오분류 수동 확인이 끝난 뒤 `_CODING_EDIT_INTENT_PATTERNS` fallback 제거 여부를 결정한다. 현재 edit/read-only 분리는 이 정규식에 의존한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:64-76`, `packages/agent-core/src/agent_core/supervisor.py:87-90`, `packages/agent-core/src/agent_core/supervisor.py:280-285`)
- [ ] `_RUNTIME_VERIFY_PATTERNS`는 `verify` intent 안정화 뒤 제거 여부를 별도 결정한다. 현재 runtime verifier 호출은 이 정규식과 review state에 의존한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:56-62`, `packages/agent-core/src/agent_core/supervisor.py:273-277`, `packages/agent-core/src/agent_core/supervisor.py:745-754`)
- [ ] Research/data_science는 regex 제거 대상이 아니라 state/review guard 정리 대상이다. 기존 pass/fail/artifact guard는 loop prevention 역할을 하므로 유지 또는 별도 plan으로 분리한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:647-701`, `.claude/skills/langgraph-graph-patterns/SKILL.md:53-58`)
- [ ] cleanup 후 route/SSE contract와 frontend `StreamRouteEvent`가 최종 field set과 일치하는지 integration QA를 수행한다. (근거: `.claude/skills/integration-qa-protocol/SKILL.md:34-56`, `.claude/skills/integration-qa-protocol/SKILL.md:115-122`)

검증:
- [ ] `uv run pytest tests/test_coding_supervisor.py tests/test_supervisor.py tests/test_team_subgraphs.py tests/test_api.py tests/test_chat_turn_lifecycle.py -v`를 실행한다. (근거: `apps/backend/tests/test_coding_supervisor.py:20-108`, `apps/backend/tests/test_supervisor.py:388-520`, `apps/backend/tests/test_supervisor.py:891-993`, `apps/backend/tests/test_api.py:237-249`)
- [ ] `cd apps/frontend && npm run test -- src/app/page.test.tsx`를 실행한다. (근거: `apps/frontend/package.json:5-11`, `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx:1410-1485`)

## 완료 기준

- `Router`, `RouteEntry`, SSE `route`, frontend `StreamRouteEvent`, `.claude/skills/sse-contract/SKILL.md`가 모두 optional `intent` field에 대해 일치한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:385-391`, `packages/agent-core/src/agent_core/state.py:12-20`, `apps/backend/api/routes/chat.py:653-668`, `apps/frontend/src/types/agent.ts:58-69`, `.claude/skills/sse-contract/SKILL.md:57-76`)
- Coding/research/data_science supervisor prompt가 prompt-kit 안에서만 갱신되어 있고, 각 team builder가 해당 prompt를 계속 주입한다. (근거: `packages/prompt-kit/src/prompt_kit/prompts.py:56-112`, `apps/backend/workflow/teams/research.py:25-32`, `apps/backend/workflow/teams/data_science.py:42-51`, `apps/backend/workflow/teams/coding.py:58-67`)
- Deterministic override는 `intent`를 1차 신호로 쓰고, 누락/unknown일 때만 기존 regex 또는 state/review fallback으로 동작한다. (근거: `packages/agent-core/src/agent_core/supervisor.py:647-770`)
- 기존 graph 규약을 유지한다: LLM 초기화는 `init_chat_model`, worker 생성은 `create_agent`, prompt는 prompt-kit 단일 출처다. (근거: `apps/backend/workflow/main_graph.py:19-25`, `packages/agent-core/src/agent_core/builder.py:39-46`, `packages/prompt-kit/src/prompt_kit/prompts.py:1-7`)

## 참조

- `packages/agent-core/src/agent_core/supervisor.py:19-90`, `packages/agent-core/src/agent_core/supervisor.py:385-987`
- `packages/agent-core/src/agent_core/state.py:12-96`
- `packages/prompt-kit/src/prompt_kit/prompts.py:56-112`
- `apps/backend/api/routes/chat.py:653-668`, `apps/backend/api/routes/chat.py:1170-1335`, `apps/backend/api/routes/chat.py:1568-1588`, `apps/backend/api/routes/chat.py:1915-2028`, `apps/backend/api/routes/chat.py:2248-2288`
- `apps/frontend/src/types/agent.ts:58-69`, `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx:1410-1485`
- `.claude/skills/sse-contract/SKILL.md:57-76`, `.claude/skills/integration-qa-protocol/SKILL.md:34-56`, `.claude/skills/langgraph-graph-patterns/SKILL.md:37-52`
