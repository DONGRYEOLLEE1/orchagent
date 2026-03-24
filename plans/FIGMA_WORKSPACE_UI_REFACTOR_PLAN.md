---
작업명: Figma Workspace UI Refactor Plan
간단요약: Figma OrchAgent 메인 워크스페이스와 로그인 시안을 현재 프로젝트에 이식하고, reasoning summary·tool calling statuses·추천 질문 UX를 제품 기능과 맞물리게 재구성한다.
작성일시: 2026-03-24 13:47 KST
최종 수정일시: 2026-03-24 13:53 KST
---

# Figma Workspace UI Refactor Plan

## 목표

- Figma `OrchAgent` 파일의 메인 워크스페이스(`25:2`)와 로그인 화면(`46:3`)을 현재 Next.js UI에 맞게 재구성한다.
- 현재 기능을 유지한 채 UI를 3열 명령 센터형 레이아웃으로 리팩토링한다.
- 오른쪽 패널은 계정 관리 패널이 아니라 실시간 오케스트레이션 텔레메트리 패널로 재정의한다.
- `Inner Monologue`는 AI의 `reasoning summary` 스트림을 실시간으로 보여주는 패널로 구현한다.
- `Suggested Queries`는 현재 활성 스레드의 최신 `user -> assistant` 문답 1쌍만 참조해, 최종 답변 표출 완료 후 별도 경량 모델 호출로 생성한다.
- `Tool Calling Statuses`는 응답 생성 중 한 줄짜리 상태 요약으로 중앙 채팅 영역에서 바로 보이게 한다.

## Figma 범위와 제외 범위

### Figma 소스 오브 트루스

- 메인 워크스페이스: `25:2`
- 로그인 화면: `46:3`

### 구현 제외

- [ ] 하단 푸터/빈 레이아웃 영역 `46:2`는 구현 범위에서 제외한다.
- [ ] Figma 상단 메뉴 중 실제 구현 대상은 `Chat`만으로 고정한다.
- [ ] `Dashboard`, `Agents`, `Logs`, `Settings`는 이번 리팩토링의 구현 범위에서 제외한다.
- [ ] 위 4개 메뉴는 향후 최종 제품에 모두 들어간다고 가정하지 않는다. 일부만 채택되거나 전부 제외될 수 있다.
- [ ] 존재하지 않는 기능을 시각만 맞추기 위해 더미 링크나 깨진 라우트를 추가하지 않는다.

## 현재 구조 진단

### 프런트엔드

- `apps/frontend/src/app/page.tsx`
  - 워크스페이스 레이아웃, 채팅 스트림, 오른쪽 액션 패널, 입력창 로직이 한 파일에 과도하게 결합되어 있다.
- `apps/frontend/src/components/sidebar/ThreadListSidebar.tsx`
  - 스레드 리스트는 이미 별도 컴포넌트이지만, Figma의 레이아웃/타이포그래피/밀도와 차이가 크다.
- `apps/frontend/src/components/sidebar/AgentTimeline.tsx`
  - 타임라인 데이터는 이미 있으나 카드 구조와 정보 계층이 Figma와 다르다.
- `apps/frontend/src/lib/workspace-state.ts`
  - live thread, action space, stream session 상태는 있으나 suggested queries나 telemetry-hydration 상태는 없다.

### 백엔드

- `apps/backend/api/routes/chat.py`
  - `reasoning`, `tool_start`, `tool_end`, `tool_error`, `status`, `route`, `checkpoint` 스트림 이벤트는 이미 있다.
  - `reasoning_summary`와 `text_summary`는 `trace_events`에 요약 이벤트로 저장된다.
- `apps/backend/api/routes/threads.py`
  - thread list/detail/title patch만 있고, sidebar telemetry나 suggested queries API는 없다.
- `apps/backend/services/thread_service.py`
  - thread detail은 메시지만 반환하며 reasoning summary나 추천 질문을 복원하지 않는다.

### 이미 활용 가능한 기반

- [ ] live reasoning SSE는 신규 백엔드 스트림 포맷 추가 없이 재사용한다.
- [ ] live tool events도 신규 SSE 이벤트 없이 재사용한다.
- [ ] AI thread title 생성 로직은 그대로 유지하고, 왼쪽 패널은 텍스트 중심으로 단순화한다.
- [ ] thread_profiles 스키마는 pin/title 중심으로 유지하고, 추천 질문 저장은 `trace_events` 재사용을 우선 검토한다.

## 시각/상호작용 원칙

### Visual Thesis

- 어두운 제어실형 레이아웃 위에 청록 계열 포인트를 얇게 쓰는, 밀도 높은 오케스트레이션 워크스페이스로 정리한다.

### Content Plan

- 왼쪽: 스레드 아카이브와 새 채팅 진입
- 중앙: 대화 본문과 실시간 응답 진행 상태
- 오른쪽: 에이전트 타임라인, reasoning summary, 후속 질문

### Interaction Thesis

- 스레드 행과 액션 버튼은 hover affordance를 강하게 준다.
- 응답 생성 중에는 중앙 영역의 tool status 줄과 오른쪽 reasoning panel이 동시에 살아 움직여야 한다.
- 추천 질문은 최종 답변 완료 뒤 자연스럽게 나타나야 하며, 최종 답변 스트리밍을 절대 막지 않는다.

## 구현 불변 조건

- [ ] 최종 답변 스트리밍 동작과 기존 duplicate-response fix를 깨뜨리지 않는다.
- [ ] HITL interrupt/resume 경로를 유지한다.
- [ ] 스레드 pin/rename/delete, AI thread title 생성 기능을 유지한다.
- [ ] 로그인/회원가입/비밀번호 변경 플로우의 기능적 동작을 유지한다.
- [ ] 모바일에서 좌측 패널 drawer 동작은 계속 지원한다.

## 권장 아키텍처 결정

### 1. 워크스페이스 레이아웃 분해

- `page.tsx`의 거대 컴포넌트를 shell + panel 컴포넌트 조합으로 분해한다.
- 권장 분해:
  - `WorkspaceShell`
  - `WorkspaceTopNav`
  - `ThreadRail`
  - `ChatWorkspace`
  - `TelemetrySidebar`
  - `ReasoningSummaryPanel`
  - `SuggestedQueriesPanel`
  - `LiveToolStatusStrip`

### 2. 계정 관리 패널 재배치

- `ProfilePanel`, `AdminStatusPanel`은 오른쪽 telemetry 영역에서 제거한다.
- 상단 우측 프로필 버튼에 연결된 drawer 또는 modal로 이동한다.
- 이유:
  - Figma 우측 패널은 실시간 오케스트레이션 정보 전용이다.
  - 현재 `Action Space`에 계정 폼이 섞여 있어 정보 위계가 무너진다.

### 3. Reasoning Summary 계약

- live turn에서는 기존 SSE `reasoning` 이벤트를 누적해 `Inner Monologue` 패널에 실시간 반영한다.
- historical thread 선택 시에는 최신 `reasoning_summary` trace event를 hydrate해서 보여준다.
- reasoning 원문이 아니라 summary만 보여준다.

### 4. Tool Calling Statuses 계약

- live tool cards는 유지하되, Figma 대응용으로 중앙 assistant 응답 상단에 1줄짜리 compact status strip을 추가한다.
- source는 기존 `tool_start`, `tool_end`, `tool_error` 이벤트를 사용한다.
- 표출 규칙:
  - 최근 실행/완료된 1~3개 항목만 노출
  - display name이 있으면 우선 사용
  - 길면 truncate
  - state 색상만 미세하게 구분

### 5. Suggested Queries 계약

- 생성 시점:
  - 현재 active thread의 최종 답변이 모두 표출된 뒤
  - `status = completed`를 확인한 후 비동기 후처리로 실행
- 입력 컨텍스트:
  - 최신 user message 1개
  - 그에 대응하는 최신 assistant final answer 1개
- 출력 개수:
  - 3~4개
- 출력 형식:
  - 한국어 우선
  - 한 줄
  - 클릭 즉시 입력창에 주입 또는 바로 전송 가능한 길이
- 저장 전략:
  - v1에서는 `trace_events`에 `suggested_queries_summary` 이벤트로 저장해 thread 재선택 시 복원한다.
  - 별도 DB 테이블 추가는 1차 범위에서 피한다.

### 6. 모델/프롬프트 계약

- 새 시스템 프롬프트는 반드시 `packages/prompt-kit/src/prompt_kit/prompts.py`에 추가한다.
- 추천 질문 생성 모델은 경량 모델 계열을 설정값으로 주입하고, 백엔드 런타임 초기화는 `init_chat_model`만 사용한다.
- 추천 질문 생성은 메인 답변 생성과 순차 종속되면 안 되며, answer-complete 이후 별도 호출로 동작한다.

## 단계별 구현 체크리스트

## Phase 0. 범위 고정과 데이터 계약 문서화

- [x] Figma 구현 범위를 `25:2`, `46:3`으로 고정하고 `46:2` 제외를 명시한다.
- [x] 우측 패널의 실시간 역할을 `timeline + reasoning summary + suggested queries`로 고정한다.
- [x] `ProfilePanel`, `AdminStatusPanel` 이동 원칙을 고정한다.
- [x] `reasoning_summary`는 live SSE + historical trace hydrate 혼합 방식으로 간다는 계약을 문서화한다.
- [x] `suggested_queries`는 final answer 완료 후 실행되고 main answer를 block하지 않는다는 계약을 문서화한다.
- [x] `suggested_queries_summary` trace event 사용 여부를 최종 확정한다.

검증:

- [x] 계획서와 현재 코드 구조가 충돌하지 않는지 재검토한다.
- [x] 현재 SSE 이벤트 계약만으로 reasoning/tool strip 구현이 가능한지 확인한다.

## Phase 1. 디자인 토큰과 레이아웃 셸 정비

- [ ] `apps/frontend/src/app/layout.tsx`와 `globals.css`를 Figma 톤에 맞는 전역 토큰 구조로 재편한다.
- [ ] 기본 타이포그래피 체계를 정리한다.
- [ ] 워크스페이스 3열 레이아웃 토대를 만든다.
- [ ] 모바일 drawer와 데스크톱 고정 레일의 공통 구조를 만든다.
- [ ] 상단 브랜드/프로필/세션 chrome을 Figma 톤에 맞게 재배치한다.
- [ ] 상단 메뉴는 `Chat`만 실구현하고, 나머지는 실제 네비게이션 기능을 연결하지 않는다.
- [ ] 향후 채택 여부가 미정인 메뉴는 disabled 또는 non-interactive visual state로만 처리한다.

검증:

- [ ] `npm run lint`
- [ ] `npm run test -- src/app/page.test.tsx`
- [ ] `npm run build`

## Phase 2. 좌측 Threads 레일 리팩토링

- [ ] `ThreadListSidebar`를 Figma 좌측 레일 밀도와 계층으로 재구성한다.
- [ ] 현재 스레드명 좌측 아이콘은 추가하지 않는다.
- [ ] AI 생성 스레드명이 가장 잘 읽히도록 타이포와 여백을 재조정한다.
- [ ] `New Chat`, pinned state, hover actions, selection state를 시안 톤에 맞춘다.
- [ ] 스크롤 영역과 empty state를 Figma 스타일에 맞게 조정한다.
- [ ] 현재 pin-to-top 동작과 rename/delete 메뉴를 유지한다.

검증:

- [ ] `npm run test -- src/components/sidebar/ThreadListSidebar.test.tsx src/app/page.test.tsx`
- [ ] 수동 브라우저 확인: hover, rename, pin, delete, mobile drawer

## Phase 3. 중앙 Chat Workspace 리팩토링

- [ ] 사용자/assistant message 레이아웃을 Figma 스타일로 재정렬한다.
- [ ] assistant 응답 컨테이너를 Figma의 integrated response card 스타일로 재구성한다.
- [ ] `LiveToolStatusStrip` 컴포넌트를 추가한다.
- [ ] 입력창, 첨부 버튼, send 버튼을 Figma의 검은 입력 바와 청록 CTA 톤으로 정렬한다.
- [ ] 현재 markdown/code/table 렌더링이 새 레이아웃에서도 깨지지 않도록 조정한다.
- [ ] interrupt/resume panel이 새 채팅 컬럼 안에서 어색하지 않게 보이도록 재배치한다.

검증:

- [ ] `npm run test -- src/app/page.test.tsx src/lib/chat-stream.test.mjs`
- [ ] 복합 질의 스트림 중 tool status 줄이 실시간 갱신되는지 수동 확인
- [ ] direct completion과 finalizer 경로 모두 assistant card가 정상 표출되는지 확인

## Phase 4. 우측 Telemetry Sidebar 구현

- [ ] `Action Space`를 폐기하거나 명칭을 제거하고 Figma식 telemetry sidebar로 교체한다.
- [ ] `AgentTimeline`을 Figma 카드 구조로 재작성한다.
- [ ] `ReasoningSummaryPanel`을 추가해 live reasoning chunk를 실시간 누적한다.
- [ ] historical thread 선택 시 latest `reasoning_summary`를 hydrate하는 상태를 추가한다.
- [ ] raw debug panel은 기본 숨김 보조 영역으로 축소하거나 개발자용 collapsible로 분리한다.
- [ ] `ProfilePanel`, `AdminStatusPanel`을 상단 프로필 액션으로 이동한다.

검증:

- [ ] `npm run test -- src/app/page.test.tsx`
- [ ] reasoning SSE가 panel에 누적되는지 단위 테스트 추가
- [ ] historical thread 선택 시 reasoning summary fallback/hydration 확인

## Phase 5. Suggested Queries 백엔드/프런트 계약 구현

- [ ] `packages/prompt-kit`에 추천 질문 생성 프롬프트를 추가한다.
- [ ] 추천 질문 생성용 response schema를 정의한다.
- [ ] 백엔드 service를 추가해 latest user/assistant pair 기준으로 3~4개 질문을 생성한다.
- [ ] `init_chat_model` 기반 경량 모델 초기화 설정을 추가한다.
- [ ] `POST /api/threads/{thread_id}/suggested-queries` 엔드포인트를 추가한다.
- [ ] 생성 결과를 `trace_events`의 `suggested_queries_summary`로 저장한다.
- [ ] historical hydrate용 조회 로직을 `ThreadService` 또는 별도 telemetry service에 추가한다.
- [ ] 프런트에 추천 질문 상태와 요청 수명주기 관리를 추가한다.
- [ ] 현재 active thread의 final answer 완료 후 추천 질문 생성 요청을 비동기로 시작한다.
- [ ] 추천 질문 생성 실패 시 메인 대화 UX에는 영향이 없도록 한다.
- [ ] thread 전환, 새 질문 시작, 삭제 시 stale suggestion response를 폐기한다.

검증:

- [ ] backend pytest: service normalization, authorization, latest-pair selection, trace persistence
- [ ] frontend test: completion 후에만 호출되는지, stale response 무시되는지, 클릭 시 입력 반영되는지
- [ ] `npm run build`

## Phase 6. Thread Detail 및 Historical Telemetry Hydration

- [ ] `GET /api/threads/{thread_id}` 응답 확장 또는 별도 telemetry endpoint를 설계한다.
- [ ] historical selection 시 reasoning summary와 suggested queries를 복원한다.
- [ ] v1에서 historical tool execution full replay를 하지 않을 경우, 명확한 empty/fallback copy를 정의한다.
- [ ] live thread와 historical thread UI copy를 구분해 오해를 줄인다.

검증:

- [ ] backend pytest: historical telemetry retrieval
- [ ] frontend test: thread selection 시 sidebar hydrate

## Phase 7. 로그인/회원가입 화면 시안 적용

- [ ] 로그인 페이지를 Figma `46:3` 톤으로 재구성한다.
- [ ] 회원가입 페이지는 동일한 디자인 시스템으로 파생 구현한다.
- [ ] 현재 인증 플로우와 validation 동작은 유지한다.
- [ ] must-change-password 화면도 동일한 디자인 계열로 정리한다.

검증:

- [ ] `npm run test -- src/app/auth-flow.test.tsx`
- [ ] `npm run build`
- [ ] 로그인, 회원가입, 로그아웃, 강제 비밀번호 변경 수동 확인

## Phase 8. 회귀 테스트와 실브라우저 최종 검증

- [ ] 프런트 주요 상태 전환 테스트를 정리한다.
- [ ] 백엔드 suggestion/telemetry 회귀 테스트를 정리한다.
- [ ] raw event 기반 기능들이 기존 duplicate-response fix와 충돌하지 않는지 확인한다.
- [ ] lint/test/build 전체 기준을 통과시킨다.

Playwright MCP 최종 체크리스트:

- [ ] 새 스레드에서 질의 전송 시 AI thread title이 정상 적용된다.
- [ ] 중앙 assistant card 상단에 tool calling status 한 줄이 실시간으로 나타난다.
- [ ] 오른쪽 `Inner Monologue`에 reasoning summary가 스트림 중 실시간으로 누적된다.
- [ ] 최종 답변 완료 후 `Suggested Queries`가 뒤늦게 나타나며, 그 전에는 로딩 또는 빈 상태를 유지한다.
- [ ] 추천 질문 클릭 시 입력창 반영 또는 전송 UX가 정상 동작한다.
- [ ] 스레드 전환 시 이전 thread의 reasoning/suggestions가 누수되지 않는다.
- [ ] pinned thread, rename, delete, interrupt/resume가 새 UI에서도 유지된다.
- [ ] 로그인 화면과 워크스페이스 화면 모두 Figma 방향성과 일관된지 최종 점검한다.

## 구현 순서 권장

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6
8. Phase 7
9. Phase 8

## 메모

- 추천 질문은 반드시 최종 답변 이후 후처리로 돌아야 하며, 메인 응답의 TTFT/스트리밍 품질을 절대 악화시키면 안 된다.
- 중앙 `Tool Calling Statuses`는 정보량보다 반응성을 우선한다.
- Figma 상의 우측 패널 정보 밀도는 유지하되, 현재 프로젝트 기능 범위를 넘는 가짜 텍스트/가짜 데이터는 넣지 않는다.
