---
name: orchagent-orchestrator
description: "OrchAgent 프로젝트(LangGraph 계층형 멀티 에이전트 + FastAPI + Next.js)의 개발·리팩토링·디버깅을 에이전트 팀으로 조율하는 메인 오케스트레이터. LangGraph 그래프 설계·수정, FastAPI/SSE 엔드포인트 추가, 워크스페이스 UI 변경, 툴/프롬프트 추가, plans/*.md 기반 구현, 경계면 버그 수사 등 `apps/`·`packages/` 코드 수정 작업은 반드시 이 스킬을 사용한다. 후속 작업: 결과 수정, 부분 재실행, 재검증, 추가 구현, 다시 실행, 플랜 이어서 진행 요청 시에도 반드시 이 스킬."
---

# OrchAgent Orchestrator

LangGraph 기반 계층형 멀티 에이전트 플랫폼 OrchAgent의 개발/유지보수 작업을 에이전트 팀으로 조율한다.

## 실행 모드: 에이전트 팀

경계면 shape 합의(SSE 이벤트, API 응답, LangGraph state)가 결과 품질을 좌우하므로 팀원 간 `SendMessage` 활발한 교환이 필수 → 에이전트 팀 모드로 운영.

## 팀 아키텍처: 감독자 + 팬아웃/팬인 + 생성-검증 복합

```
[오케스트레이터/감독자]
    ├── TeamCreate(orchagent-team)
    ├── TaskCreate(plans/*.md 기반 세분화된 태스크)
    ├── 병렬 구현 (graph-architect, backend-engineer, frontend-engineer, tool-prompt-specialist)
    ├── 점진적 QA (qa-verifier가 각 모듈 완성 직후 교차 검증)
    ├── 결과 통합 및 plans/*.md 체크오프
    └── 팀 정리
```

## 에이전트 구성

| 팀원 | subagent_type | 역할 | 주요 스킬 | 산출물 경로 |
|------|--------------|------|----------|-----------|
| graph-architect | graph-architect | LangGraph 그래프 설계·리팩토링 | langgraph-graph-patterns | `packages/agent-core/**`, `apps/backend/workflow/**` |
| backend-engineer | backend-engineer | FastAPI·SSE·DB·services·pytest | sse-contract, langgraph-graph-patterns | `apps/backend/**` |
| frontend-engineer | frontend-engineer | Next.js UI·SSE 소비·vitest | sse-contract | `apps/frontend/src/**` |
| tool-prompt-specialist | tool-prompt-specialist | 툴·프롬프트 중앙 관리 | langgraph-graph-patterns | `packages/agent-tools/**`, `packages/prompt-kit/**` |
| qa-verifier | qa-verifier | 경계면 교차 검증·테스트 집행 | integration-qa-protocol, sse-contract | `_workspace/qa_report_*.md`, PR 코멘트 |
| (리더 = 오케스트레이터) | — | 작업 분배, 통합, plans 체크오프 | plans-driven-workflow | 최종 PR/커밋 |

> **모든 팀원은 `model: "opus"` 사용.**

## 워크플로우

### Phase 0: 컨텍스트 확인 (후속 작업 지원)

1. `_workspace/` 디렉토리 존재 여부 확인
2. 실행 모드 결정:
   - **미존재** → 초기 실행. Phase 1로 진행
   - **존재 + 부분 수정 요청** → 부분 재실행. 해당 에이전트만 재호출하여 기존 산출물 갱신. 이전 QA 리포트 Read하여 미해결 항목 우선
   - **존재 + 새 입력** → 새 실행. 기존 `_workspace/`를 `_workspace_{YYYYMMDD_HHMMSS}/`로 이동
3. 관련 `plans/*.md`가 있으면 미체크 항목을 우선 태스크로 식별

### Phase 1: 작업 분석

1. 사용자 요청에서 **변경 영역** 식별 — graph / backend / frontend / tools / prompts / qa. 복수 영역 동시 가능
2. 관련 plans/docs 읽기:
   - `plans/*.md` — 구현 태스크 목록
   - `docs/*_CONTRACT.md` — 지켜야 할 계약
   - `AGENTS.md` — 강제 규약 (create_agent, prompt-kit, 커밋 워크플로우)
   - `CLAUDE.md` — 하네스 레지스트리
3. 영향 범위가 경계면에 걸치면(state 변경 + SSE 변경 + UI 변경 등) 팀원 간 사전 합의가 필요한 shape 목록 준비
4. `_workspace/` 생성(초기 실행 시)

### Phase 2: 팀 구성

```
TeamCreate(
  team_name: "orchagent-team",
  members: [
    { name: "graph-architect", agent_type: "graph-architect", model: "opus",
      prompt: "LangGraph 그래프 설계. `langgraph-graph-patterns` 스킬을 반드시 따르고, create_agent/init_chat_model 강제, 프롬프트는 prompt-kit에서만. 경계면 변경 사항은 즉시 SendMessage." },
    { name: "backend-engineer", agent_type: "backend-engineer", model: "opus",
      prompt: "FastAPI/SSE/DB/서비스 구현. `sse-contract`와 `plans-driven-workflow` 스킬 준수. 테스트 통과 전 커밋 금지." },
    { name: "frontend-engineer", agent_type: "frontend-engineer", model: "opus",
      prompt: "Next.js UI·SSE 소비. `sse-contract` 준수. 타입 제네릭 맹목 캐스팅 금지. 빌드/테스트 통과 후 커밋." },
    { name: "tool-prompt-specialist", agent_type: "tool-prompt-specialist", model: "opus",
      prompt: "툴과 프롬프트 중앙 관리. `packages/prompt-kit` 외부에 프롬프트 하드코딩 금지. 회귀 테스트까지 책임." },
    { name: "qa-verifier", agent_type: "qa-verifier", model: "opus",
      prompt: "점진적 QA 집행. `integration-qa-protocol` 스킬대로 양쪽 동시 읽기. 각 모듈 완성 즉시 교차 검증." }
  ]
)
```

**팀원 선택 규칙:** 변경 영역에 해당 에이전트만 스폰. 예: 순수 UI 변경이면 graph-architect/tool-prompt-specialist 제외. 단 qa-verifier는 거의 항상 포함.

### Phase 3: 작업 등록 (TaskCreate)

plans/*.md를 근거로 세분화. 의존 순서를 `depends_on`으로 표현.

```
TaskCreate(tasks: [
  { title: "graph: state 필드 X 추가", assignee: "graph-architect" },
  { title: "prompts: supervisor 프롬프트에 X 반영", assignee: "tool-prompt-specialist", depends_on: ["graph: state 필드 X 추가"] },
  { title: "backend: X 관련 API 추가 + SSE 이벤트 X emit", assignee: "backend-engineer", depends_on: ["graph: state 필드 X 추가"] },
  { title: "frontend: SSE 이벤트 X 파싱 + UI 표시", assignee: "frontend-engineer", depends_on: ["backend: X 관련 API 추가 + SSE 이벤트 X emit"] },
  { title: "qa: API shape ↔ 훅 교차 검증 + SSE 계약 검증", assignee: "qa-verifier", depends_on: ["backend: ...", "frontend: ..."] },
  ...
])
```

**경계면 작업 규칙:** state 추가 → 백엔드 emit → 프론트 파싱의 3단계 작업은 `graph-architect`가 shape 확정 메시지를 먼저 브로드캐스트 한 뒤 병렬 구현.

### Phase 4: 병렬 구현 + 점진적 QA

**실행 방식:** 팀원들이 공유 작업 목록에서 자체 요청(claim) + 구현 + 완료 보고.

**팀 통신 핵심 패턴:**

```
graph-architect ──SendMessage──→ backend-engineer  ("state에 `retry_count: int` 필드 추가함. supervisor 재라우팅 시 증가.")
backend-engineer ──SendMessage──→ frontend-engineer  ("/api/chat SSE에 `checkpoint` 이벤트 shape: {type: 'checkpoint', id: str, ts: str}")
frontend-engineer ──SendMessage──→ backend-engineer  ("SSE event 필드명 camelCase로 통일 가능?")
tool-prompt-specialist ──SendMessage──→ graph-architect  ("새 writer persona 추가. 필요 툴 목록 합의 필요")

모든 에이전트 ──SendMessage──→ qa-verifier  ("{파일} 모듈 완성. 검증 바랍니다.")
qa-verifier ──SendMessage──→ 해당 에이전트(s)  ("api/chat.py:120 응답이 {items:[]}인데 useThreads 훅은 배열 기대. 수정 요청")
```

**산출물 저장 규칙:**
- 중간 산출물: `_workspace/{NN}_{agent}_{topic}.md` — 설계 메모, QA 리포트
- 실제 코드 변경: 각자 해당 경로(`apps/`, `packages/`)에 직접 커밋

### Phase 5: 통합 + plans 체크오프

1. 모든 태스크 완료 확인 (`TaskList`)
2. qa-verifier 최종 리포트 Read (`_workspace/qa_report_*.md`)
3. 관련 `plans/*.md`에서 완료된 체크박스 `- [x]`로 업데이트
4. `AGENTS.md`의 커밋 규약에 따라 커밋 메시지 작성. 태스크 단위마다 이미 커밋이 나뉘어 있으면 추가 정리만
5. 검증 실패/미해결 경계면이 있으면 해당 항목만 남은 태스크로 재등록 (Phase 4 복귀)

### Phase 6: 정리

1. 팀 정리 (`TeamDelete`)
2. `_workspace/` 보존 (회귀 방지·감사 추적용)
3. 사용자에게:
   - 완료된 plans 태스크 체크박스 개수
   - 커밋 목록 + 변경 파일 요약
   - QA 통과/실패 요약
   - 다음 권장 태스크

## 데이터 흐름

```
사용자 요청 + plans/*.md
        │
        ▼
[오케스트레이터]
   TeamCreate + TaskCreate(plans 기반)
        │
        ├── graph-architect ──→ agent-core/**, workflow/**
        │         ▲
        │         │ state shape 합의 (SendMessage)
        │         ▼
        ├── backend-engineer ──→ apps/backend/**
        │         ▲
        │         │ API/SSE shape 합의 (SendMessage)
        │         ▼
        ├── frontend-engineer ──→ apps/frontend/**
        │
        ├── tool-prompt-specialist ──→ agent-tools/**, prompt-kit/**
        │
        └── qa-verifier ──→ 교차 검증 → qa_report_*.md
                           ▲
                           │ 수정 요청 SendMessage
                           ▼
                    담당 에이전트(s) 재작업

        │
        ▼
[오케스트레이터: 통합 + plans 체크오프 + 커밋 정리]
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| 팀원 1명 실패/중지 | SendMessage로 상태 확인 → 재시작. 재실패 시 해당 영역 태스크를 보류 상태로 두고 최종 보고에 명시 |
| 테스트 실패 | 해당 에이전트가 수정할 때까지 커밋 보류. QA-verifier가 재검증 |
| 경계면 shape 상충 | producer/consumer 양쪽 에이전트 모두에게 SendMessage로 합의 요청. 오케스트레이터가 중재 |
| plans/*.md와 실제 코드 불일치 | 먼저 plans를 실제 상태로 갱신 후 구현 진행 (AGENTS.md 규칙) |
| 타임아웃 | 현재까지 완료된 태스크로 부분 보고 |
| 금지 API(`create_react_agent`) 발견 | graph-architect에게 즉시 리팩토링 요청 |

## 테스트 시나리오

### 정상 흐름 — 새 SSE 이벤트 타입 추가
1. 사용자가 "워커의 retry 횟수를 프론트에 실시간 표시" 요청
2. Phase 1: 영향 영역(graph/backend/frontend/qa) 식별, `sse-contract` 참조
3. Phase 2: 4명 팀 구성
4. Phase 3: TaskCreate로 6개 태스크(state 필드 → SSE 이벤트 → 파서 → UI → 백엔드 테스트 → QA)
5. Phase 4: graph-architect가 state에 `retry_count` 추가 → backend가 `retry` 이벤트 emit → frontend가 파싱 → qa가 양쪽 shape 대조
6. Phase 5: 관련 plans 체크오프 + 커밋 `feat(ui): show worker retry count`
7. Phase 6: 팀 정리, 사용자 보고

### 에러 흐름 — 경계면 shape 불일치 발견
1. Phase 4 진행 중 qa-verifier가 `checkpoint` 이벤트의 필드명 mismatch 발견
2. qa-verifier → backend-engineer + frontend-engineer 양쪽에 SendMessage (파일:라인 + 수정안)
3. producer(backend)가 contract 문서 검토 후 어느 쪽이 정확한지 합의 → 수정
4. qa-verifier 재검증 후 통과
5. 통합 보고에 "경계면 이슈 1건 발견·수정됨"을 기록

## description 적극 트리거 키워드

초기: LangGraph 그래프 수정, FastAPI 엔드포인트 추가, SSE 이벤트 추가, 워크스페이스 UI 변경, 툴 추가, 프롬프트 수정, plans 기반 구현
후속: 다시 실행, 재실행, 업데이트, 수정, 보완, 이전 결과 개선, plans 이어서, 부분 재실행, 추가 검증
