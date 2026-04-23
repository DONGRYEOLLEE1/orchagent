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
