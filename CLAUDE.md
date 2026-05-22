# OrchAgent — Claude Code 하네스 레지스트리

OrchAgent(LangGraph 계층형 멀티 에이전트 + FastAPI + Next.js) 프로젝트에서 Claude Code가 에이전트 팀 모드로 운영되도록 구성한 하네스의 단일 참조 문서.

---

## 하네스: OrchAgent 개발·운영 팀

**목표:** LangGraph 그래프 설계·수정, FastAPI/SSE 엔드포인트 구현, Next.js 워크스페이스 UI 구현, 툴/프롬프트 관리, 경계면 버그 사전 탐지까지 전 영역을 에이전트 팀으로 병렬·교차 검증 하며 수행한다.

**실행 모드:** 에이전트 팀 (`TeamCreate` + `SendMessage` + `TaskCreate`)  
**팀 아키텍처:** 감독자 + 팬아웃/팬인 + 생성-검증 복합  
**모델:** 모든 팀원은 `model: "opus"`

---

## 🤖 에이전트 팀

| 에이전트 | 주된 영역 | 한 줄 역할 |
| :--- | :--- | :--- |
| `graph-architect` | `packages/agent-core`, `apps/backend/workflow` | LangGraph StateGraph·supervisor·validator·interrupt 설계 |
| `backend-engineer` | `apps/backend` 전반 | FastAPI·SSE·DB·services·pytest 구현 |
| `frontend-engineer` | `apps/frontend/src` | Next.js 워크스페이스 UI·SSE 소비·vitest |
| `tool-prompt-specialist` | `packages/agent-tools`, `packages/prompt-kit` | 워커 툴과 프롬프트 중앙 관리 |
| `qa-verifier` | 전 영역 (경계면 감시) | API/SSE/state/라우팅 교차 검증, 테스트 집행 |

---

## 🛠️ 스킬 (팀 공유 계약/규약)

| 스킬 | 용도 | 주 사용 에이전트 |
| :--- | :--- | :--- |
| `orchagent-orchestrator` | 에이전트 팀 조율 — 작업 영역 분석 → TeamCreate/TaskCreate → 병렬 구현 + 점진적 QA → plans 체크오프 | 오케스트레이터(리더) |
| `langgraph-graph-patterns` | `create_agent`/`init_chat_model` 강제, 프롬프트 `prompt-kit` 단일 관리, state/HITL/체크포인터 설계 규약 | `graph-architect`, `backend-engineer`, `tool-prompt-specialist` |
| `sse-contract` | 백↔프론트 SSE 이벤트(`status/route/reasoning/tool/text/checkpoint`) shape의 ground truth, OWNERSHIP 규칙 | `backend-engineer`, `frontend-engineer`, `qa-verifier` |
| `integration-qa-protocol` | 5대 경계면(API↔훅, SSE↔파서, state↔emit, 전이맵↔goto, 경로↔href) 양쪽 동시 읽기 교차 검증 절차 | `qa-verifier`(주), 생산자/소비자 에이전트 |
| `plans-driven-workflow` | 태스크→검증→체크(`- [x]`)→커밋(`type(scope): summary`)→push 루프, plans 작성 규칙, docs 저장 기준 | 전원 |

---

## 🎯 실행 규칙

- **트리거**: `apps/`·`packages/` 코드 수정, LangGraph 그래프 변경, FastAPI/SSE 엔드포인트 추가, 워크스페이스 UI 변경, 툴/프롬프트 추가, `plans/*.md` 기반 구현, 경계면 버그 수사 → `orchagent-orchestrator` 스킬로 처리
- **후속 작업**(재실행·부분 수정·재검증·plans 이어서 진행)도 동일 스킬을 사용
- **단순 질문/확인/조회**는 에이전트 팀 없이 직접 응답 가능
- **AGENTS.md 강제 규약** 항상 준수:
  - `langchain.chat_models.init_chat_model`로 LLM 초기화
  - `langchain.agents.create_agent`로 워커 구성
  - `langgraph.prebuilt.create_react_agent` 절대 사용 금지
  - 모든 프롬프트는 `packages/prompt-kit`에서만 정의·import
- **커밋 워크플로우**: 태스크 1개 → 관련 검증 통과 → `plans/*.md` 체크박스 `- [x]` 반영 → `type(scope): summary` 커밋 → push → 다음 태스크. 검증 실패 상태에서 커밋 금지.
- **경계면 작업 규칙**: state/SSE/API shape 변경은 producer가 shape 합의 메시지를 먼저 브로드캐스트한 뒤 consumer와 병렬 구현. `qa-verifier`가 모듈 완성 직후 즉시 교차 검증(점진적 QA).
- **중간 산출물** 경로: `_workspace/` (QA 리포트·설계 메모 등). 기존이 존재하면 후속 실행 시 Read하여 재사용.

---

## 🧪 테스트 코드 추가 정책 (Core-Only, 볼륨 보수)

테스트 코드는 회귀 차단 가치를 기준으로 엄격히 선별한다. **Core 카테고리에 해당하지 않으면 새 테스트 작성 금지**. 기존 테스트 안에 케이스를 추가할 때도 동일 기준으로 판단한다.

### Core 카테고리 (이 중 하나에 명확히 해당할 때만 추가)

1. **회귀 fix 검증** — 실제 발견된 버그를 재현하는 최소 케이스. 커밋 메시지/PR 본문이 그 버그를 명시할 수 있어야 한다.
2. **계약 (contract) 보장** — SSE 10종 이벤트 shape, FINAL_RESPONSE_STREAM_OWNERSHIP, RouterDecision 스키마, ToolErrorPayload 같은 인터페이스 불변.
3. **safeguard (plan §4.0 P3)** — `reject_invalid_goto` / `enforce_team_redirect_limit` / `enforce_dispatch_limit` / `fallback_decision_on_parse_failure`처럼 LLM 결정을 차단·재요청하는 안전망.
4. **통합 smoke** — `/api/chat`, `/api/threads`, `/api/auth/*` 같은 경계면이 200을 반환하는 최소 1~2 케이스.
5. **핵심 비즈니스 로직** — head/team supervisor 라우팅, finalizer 합성, validator 폴백, planner 결정 등 LangGraph 그래프 핵심 노드.

### 추가 금지 (PR 작성 전 자기 점검)

- ❌ pydantic 모델 default-value instantiation sanity (`Model().field == default`)
- ❌ service의 단순 CRUD wrapper 테스트 (SQLAlchemy 호출 1~2줄을 mock으로 검증)
- ❌ prompt 문자열 substring 일치 같은 string assertion 일변도 — prompt 변경 시 깨지기만 함
- ❌ dead feature 잔재 (Phase 2.x에서 제거된 휴리스틱·plan-driven override 등)
- ❌ 같은 함수의 input permutation 3개 이상 — `pytest.parametrize`로 한 케이스로 통합
- ❌ trivial helper 함수의 단위 테스트 (예: `_extract_text_content` 같은 1~2줄 함수)
- ❌ placeholder/skeleton 파일 (docstring만 있는 파일, `pass`만 있는 함수)

### 작성 절차

1. 새 테스트를 작성하기 전, 위 5개 Core 카테고리 중 어디에 해당하는지 1초 안에 답할 수 있어야 한다. 답이 안 나오면 작성하지 말 것.
2. 같은 기능을 검증하는 기존 케이스가 있는지 grep으로 먼저 확인. 있으면 그 케이스에 assertion을 더하거나 `parametrize`로 묶는다.
3. 신규 파일을 만들기 전, 같은 도메인의 기존 파일에 묶을 수 있는지 점검 (`tests/test_<domain>_*.py` 통합 우선).

### 외부 인용

- 회귀 정량 측정은 `apps/backend/tests/routing_eval/golden_dataset.json`이 담당. LLM 라우팅 정확도 회귀는 단위 테스트보다 evaluation harness로 잡는다 (plan §4.0 P5).
- baseline 비교는 `infra/scripts/{capture,diff}_baseline.sh`. 신규 테스트 통과 수가 baseline보다 줄어들면 곧장 회귀.

---

## 🧭 Supervisor → Sub-agent Handoff 정책 (LLM-Driven, 룰 베이스 금지)

OrchAgent 런타임의 head/team supervisor가 사용자 질의를 파악해 sub-agent(`research_team` / `coding_team` / `data_science_team` / `vision_team` / `writing_team`) 및 worker(`data_engineer`/`data_analyst`/`codebase_explorer`/`implementation_engineer`/`runtime_verifier`/`search`/`web_scraper`/...)로 위임할 때 따르는 단일 정책. **모든 분기 결정은 LLM이 `RouterDecision` structured output으로 내린다. 정규식 매칭·`_should_force_*` 함수·키워드 사전 같은 룰 베이스는 절대 추가 금지** (plan §4.0 P1).

### P1. 모든 라우팅·handoff는 LLM 결정
- head supervisor의 팀 선택, team supervisor의 worker 선택, FINISH / `request_review` / `team_finished` 판단은 모두 `RouterDecision`(`agent_core/router_schema.py`) JSON 응답으로 결정.
- 코드에서 사용자 텍스트를 정규식·키워드로 검사해 "강제 라우팅"하는 패턴은 만들지 말 것. 기존 `_APPROVAL_PATTERNS` / `_should_force_coding_team` 등은 Phase 2.2 라운드에서 모두 제거됨 — **부활시키지 말 것**.
- 새 분기 의도가 생기면 `packages/prompt-kit/src/prompt_kit/prompts.py`의 supervisor / worker 프롬프트에 한 줄 가이드만 추가해서 LLM이 스스로 그 결정을 내리도록 유도.

### P2. 프롬프트가 단일 출처
- 라우팅 의도(이미지 → `vision_team`, 첨부 데이터 → `data_science_team` 등)는 `SYSTEM_SUPERVISOR_PROMPT` (`# TEAM SELECTION HINTS`)에만 정의.
- worker 책임 분담(data_engineer는 1패스 검사, data_analyst는 차트 생성)은 해당 worker prompt에만 정의.
- handoff 시점 가이드(예: "data_engineer 다음은 항상 data_analyst")는 `TEAM_SUPERVISOR_PROMPT`의 `# DATA SCIENCE TEAM HANDOFF` 같은 블록에 명시.
- 같은 의도를 코드(`supervisor.py`)·프롬프트 양쪽에 중복 작성 금지. prompt-kit이 진실.

### P3. 안전망(safeguard)은 차단/재요청만, 결정 변경 금지
- `agent_core/safeguards.py`의 4개 함수만 사용:
  - `reject_invalid_goto` — LLM이 그래프에 없는 노드 지정 시 FINISH로 강제 (재요청 1회 후)
  - `enforce_team_redirect_limit` — head가 같은 팀으로 N회 반복 redirect 시 FINISH
  - `enforce_dispatch_limit` — team supervisor가 worker dispatch 한도 초과 시 FINISH
  - `fallback_decision_on_parse_failure` — structured output 파싱 실패 시 FINISH
- safeguard는 LLM의 valid 결정을 **다른 결정으로 바꾸지 않는다**. 차단(FINISH) 또는 재요청(retry)만.
- 새 safeguard 추가 시도는 일반적으로 거부 — 먼저 prompt 수정으로 LLM이 그 상황을 직접 처리하도록 시도하고, 그래도 못 막을 때만 P3 safeguard로 추가.

### P4. 결정은 사용자/UI에 가시화
- 모든 supervisor 결정은 `route_history` 항목으로 누적되어 SSE `route` 이벤트로 emit, 프론트 `Inner Monologue` 패널에 reason 노출.
- safeguard 발동 시 reason 문자열이 `safeguard: …` 접두어를 가져야 사용자가 안전망 작동임을 식별 가능.

### P5. 회귀는 evaluation harness로 측정
- 라우팅 정확도 회귀는 `apps/backend/tests/routing_eval/`의 골든 데이터셋 + scorer로 측정.
- 새 의도 카테고리를 추가하면 `golden_dataset.json`에 케이스를 함께 추가하고, top-1 정확도 ≥ 95% 유지를 목표.
- 휴리스틱 추가 충동이 생기면 P5의 evaluation 결과로 먼저 정량 입증할 것.

### Handoff 점검 체크리스트 (PR 작성 전)
- [ ] 라우팅 의도가 prompt-kit 외부(`supervisor.py`/`planner.py`/`chat.py`)에 인코딩되어 있지 않은가?
- [ ] 새 정규식·`_should_force_*`·키워드 패턴이 도입되지 않았는가? (`grep -rn "_should_force_\|_APPROVAL_PATTERNS" packages/agent-core` 결과 0건 유지)
- [ ] safeguard 4종 외 새 룰이 supervisor 본체에 추가되었다면, 동등한 prompt 가이드로 대체할 수 있는가?
- [ ] `routing_eval` 골든셋에 새 의도가 반영됐는가?

---

## 📁 디렉토리 구조

```
.claude/
├── agents/
│   ├── graph-architect.md
│   ├── backend-engineer.md
│   ├── frontend-engineer.md
│   ├── tool-prompt-specialist.md
│   └── qa-verifier.md
├── skills/
│   ├── orchagent-orchestrator/SKILL.md
│   ├── langgraph-graph-patterns/SKILL.md
│   ├── sse-contract/SKILL.md
│   ├── integration-qa-protocol/SKILL.md
│   └── plans-driven-workflow/SKILL.md
└── settings.local.json
```

---

## 🔗 주요 참조 경로

| 경로 | 역할 |
| :--- | :--- |
| `AGENTS.md` | 코드 변경 전 반드시 읽어야 할 강제 규약(LLM/워커/프롬프트/plans 워크플로우/커밋 컨벤션) |
| `README.md` | 프로젝트 개요, 아키텍처 다이어그램, 기동 방법 |
| `plans/*.md` | 구현 태스크 단위 계획서(phase 기반 체크리스트) |
| `docs/*_CONTRACT.md` | 지켜야 할 런타임 계약 — 특히 `FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT.md` |
| `docs/*_RESEARCH_REPORT.md`, `docs/architecture-improvement-analysis.md` | 의사결정 근거·조사 결과 |
| `apps/backend/workflow/main_graph.py` | 최상위 그래프 컴파일·체크포인터 장착 |
| `packages/agent-core/src/agent_core/` | state·supervisor·validator·builder·personalization |
| `packages/agent-tools/src/agent_tools/` | web/vision/coding/runtime/file_io/data 툴 |
| `packages/prompt-kit/src/prompt_kit/prompts.py` | 모든 시스템·워커·validator 프롬프트 단일 출처 |
| `apps/frontend/src/lib/chat-stream.*`, `workspace-state.ts` | SSE 소비·워크스페이스 상태 머신 |
| `infra/scripts/start-dev.sh` | 전체 스택 dev 모드 기동 |

---

## 📅 변경 이력

| 날짜 | 변경 내용 | 대상 | 사유 |
| :--- | :--- | :--- | :--- |
| 2026-04-19 | 하네스 전면 재구성 — 구 5 에이전트/11 스킬 삭제, 신규 5 에이전트/5 스킬로 재설계 | 전체 | 구 하네스가 저성능 로컬 모델로 생성되어 지침 품질이 낮았음. OrchAgent의 실제 프로젝트 구조(감독자 패턴 + 경계면 QA 중심)와 AGENTS.md 강제 규약을 반영한 팀 구성으로 교체 |
