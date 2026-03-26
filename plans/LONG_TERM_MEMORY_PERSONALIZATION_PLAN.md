---
작업명: Long-Term Memory Personalization & Settings Plan
간단요약: Figma settings 디자인을 기준으로 OrchAgent에 전용 Settings 화면, Profile/Change Password, Personal Memory 카드 인터랙션, KST 저장 시각, memory sidecar agent, 런타임 장기기억 personalization 경로와 엄격한 성능 검증 체계를 단계적으로 도입한다.
작성일시: 2026-03-26 09:59 KST
최종 수정일시: 2026-03-26 11:36 KST
---

# Long-Term Memory Personalization & Settings Plan

## 배경

기존 계획은 memory 기능 자체에 초점이 있었고, settings 화면은 `AccountDrawer` 확장 정도로 가정했다. 하지만 이번 요구사항은 그 수준으로 처리하면 안 된다.

- Figma에는 전용 settings 프레임이 따로 있다.
- 기존 chat 화면의 `TopNavBar` 좌측 정렬 규칙을 유지해야 한다.
- `Profile` 안에서 `Change Password`가 first-class 화면으로 다뤄져야 한다.
- `Personal Memory`는 단순 CRUD list가 아니라 hover action, `...` 메뉴, 저장일 상태 문구, KST 적재 규칙까지 포함하는 제품 인터랙션이다.
- memory 기능은 retrieval 성능, turn latency, DB 부하를 직접 건드리므로 성능 검증을 기능 검증과 같은 수준으로 다뤄야 한다.
- 사용자 성향/선호를 자동 추출하는 `memoryAgent`류 구성은 유효하지만, 사용자 응답 경로와 같은 critical path에 넣으면 latency와 라우팅 복잡도가 급증한다.

따라서 이 작업은 “memory panel 추가”가 아니라 `전용 Settings IA + UI shell + profile/password surface + personal memory data/UI + runtime memory integration`으로 봐야 한다.

## 디자인 입력

### Figma 확인 결과

2026-03-26에 Figma MCP를 먼저 시도했으나 starter plan rate limit으로 막혔고, 동일 파일을 Playwright로 직접 확인했다.

- Figma 파일
  - `https://www.figma.com/design/si827bWNqDEpK7YoR3wW4r/OrchAgent`
- 확인한 settings 노드
  - `Settings-Profile`: `node-id=96:2`
  - `Settings-PersonalMemory`: `node-id=98:183`
- Playwright에서 선택 시 확인된 프레임 메타
  - 두 프레임 모두 폭 `1280`
  - `Settings-Profile` 높이 `1219`
  - `Settings-PersonalMemory` 높이 `1157`
  - 선택 프레임은 top-left 기반 auto-layout으로 보인다

### 로컬 코드 기준 레퍼런스

- 기존 `WorkspaceTopNav`는 브랜드와 섹션 네비게이션이 좌측에 몰려 있는 구조다.
- 현재 `Settings` 버튼은 존재하지만 disabled 상태다.
- 현재 account 관련 설정은 `AccountDrawer`에 있고, 이는 전용 settings 화면 요구를 충족하지 못한다.
- 기존 overflow interaction 레퍼런스는 `ThreadListItem`의 hover `...` 메뉴다.
- 현재 change password 화면은 `must_change_password` 강제 흐름 안의 `AuthScaffold` form으로만 존재한다.

## 목표

- Figma settings 프레임을 기준으로 전용 Settings 화면을 도입한다.
- Settings의 top navigation은 chat/dashboard와 동일하게 `왼쪽 정렬`을 유지한다.
- `Settings-Profile`에서 프로필 수정과 `Change Password`를 분리된 중요 섹션으로 구현한다.
- `Settings-PersonalMemory`에서 memory card hover interaction과 삭제 UI를 구현한다.
- 각 memory 항목에는 KST 기준 저장 시각을 적재하고, UI에서 `2026년 03월 26일에 저장되었음` 형식으로 노출한다.
- 이후 memory read/write와 personalization runtime을 해당 settings surface와 연결한다.
- memory 기능 도입 후에도 기존 chat 응답 latency와 TTFT를 허용 범위 내로 유지한다.

## 범위

- 포함
  - 전용 settings route/layout/shell
  - `WorkspaceTopNav`의 settings 활성화 및 좌측 정렬 규칙 유지
  - profile settings
  - change password settings UI
  - personal memory table/API/UI
  - KST timestamp 적재 및 표시
  - memory sidecar agent 또는 동등한 비동기 extraction pipeline
  - runtime memory retrieval/injection
  - inferred memory와 temporary chat 확장
  - 성능 게이트, 부하 테스트, 회귀 성능 검증
- 제외
  - 조직/프로젝트/팀 entity 신설
  - 외부 vector DB 즉시 도입
  - settings 외의 전체 workspace visual redesign

## 현재 구조 진단

### 프런트엔드

- `apps/frontend/src/components/workspace/WorkspaceTopNav.tsx`
  - 좌측에 브랜드와 nav를 두는 canonical top nav다.
  - 현재 type은 `'chat' | 'dashboard'`만 지원한다.
  - `Settings` 버튼은 disabled 상태라 실제 route 연결이 없다.
- `apps/frontend/src/components/workspace/AccountDrawer.tsx`
  - 현재 profile/admin controls를 오른쪽 drawer에 담고 있다.
  - settings 전용 information architecture를 담기엔 폭과 상호작용이 부족하다.
- `apps/frontend/src/components/auth/ProfilePanel.tsx`
  - display name/email 편집만 제공한다.
- `apps/frontend/src/app/page.tsx`
  - change password form은 bootstrap admin 전용 강제 변경 흐름에만 존재한다.
- `apps/frontend/src/components/sidebar/ThreadListItem.tsx`
  - hover 시 `...`가 나타나고 menu가 열리는 패턴이 있어 personal memory action의 가장 가까운 UI 레퍼런스다.

### 백엔드

- `apps/backend/models/auth.py`, `logging.py`, `analytics.py`
  - user/thread/turn 축은 이미 있다.
- memory canonical table은 아직 없다.
- `shared_context`에는 approval flag만 들어가고 personalization 정보는 없다.
- prompt-kit에는 memory 사용 규칙이 없다.
- KST timestamp 적재 패턴은 기존 모델에서 이미 사용 중이다.
- 별도 benchmark/load-test harness는 아직 없다.

## UI/UX 계약

### Settings Shell

- settings는 drawer가 아니라 전용 route로 간다.
- 권장 route 구조
  - `/settings/profile`
  - `/settings/personal-memory`
- desktop에서는 settings 내부 좌측 rail 또는 section nav를 둔다.
- mobile에서는 같은 정보 구조를 stacked layout으로 폴백한다.
- 상단 `WorkspaceTopNav`는 기존 chat 화면과 동일한 좌측 정렬을 유지한다.
- settings 화면 때문에 top nav를 가운데 정렬하거나 오른쪽 정렬로 재배치하지 않는다.

### Settings-Profile

- profile edit와 password change를 한 카드에 섞지 않고, 시각적으로 분리된 섹션으로 둔다.
- `Change Password`는 current/new 입력만 복제하는 수준으로 끝내지 않는다.
- 최소 요구사항
  - 현재 비밀번호
  - 새 비밀번호
  - 새 비밀번호 확인
  - 비밀번호 규칙 안내
  - inline error
  - success feedback
  - submitting/loading state
- 기존 bootstrap 강제 변경 흐름과 settings용 password form은 중복 구현하지 말고 공유 가능한 컴포넌트로 합친다.

### Settings-PersonalMemory

- 각 memory card는 hover/focus 시에만 우측 `...` 액션이 노출된다.
- interaction reference는 `ThreadListItem`의 hover action 패턴을 따른다.
- `...`를 누르면 최소 두 요소가 보여야 한다.
  - `삭제` 액션
  - 하단 상태 설명
- 상태 설명 카피는 저장 시각 기준이며 예시 형식은 아래와 같다.
  - `2026년 03월 26일에 저장되었음`
- 저장 시각은 UI 렌더링 기준 local guess가 아니라 `DB에 KST 기준으로 적재된 created_at`을 기준으로 한다.
- memory card는 keyboard focus에서도 `...` 메뉴에 접근 가능해야 한다.
- empty/loading/error state를 별도 설계한다.

## 데이터 계약

### 1. `user_memory_settings`

사용자 단위 memory 토글과 향후 확장 정책을 저장한다.

- `user_id PK/FK -> auth_users.id`
- `memory_enabled`
- `allow_explicit_memory`
- `allow_inferred_memory`
- `allow_chat_history_reference`
- `default_memory_mode`
- `created_at`
- `updated_at`

### 2. `user_memory_entries`

personal memory card의 canonical source다. 이번 요구사항의 “DB 테이블 하나 추가”는 최소한 이 테이블을 뜻한다.

- `id UUID PK`
- `user_id FK`
- `thread_id NULL FK`
- `scope_type`
- `source_type`
- `status`
- `category`
- `title`
- `content_text`
- `content_json`
- `confidence`
- `salience`
- `created_from_turn_id NULL FK`
- `last_used_at NULL`
- `use_count`
- `created_at`
- `updated_at`
- `deleted_at NULL`

### 3. `memory_reference_events`

어떤 turn이 어떤 memory를 실제 사용했는지 추적한다.

- `id UUID PK`
- `user_id FK`
- `thread_id FK`
- `turn_id FK`
- `memory_id FK`
- `phase`
- `rank`
- `reason`
- `created_at`

### KST 적재 규칙

- `user_memory_entries.created_at`와 `updated_at`는 timezone-aware KST로 저장한다.
- 기존 모델과 동일하게 KST helper/default 패턴을 사용한다.
- API는 timezone 정보가 보존된 ISO timestamp를 반환한다.
- 프런트는 `Asia/Seoul` 기준 formatter로 `YYYY년 MM월 DD일` 문구를 만든다.

## 권장 Memory Agent 아키텍처

### 결론

`memoryAgent`를 두는 방향 자체는 타당하다. 다만 이 프로젝트에서는 `head supervisor`가 매 turn마다 라우팅하는 새 팀으로 넣는 것보다, `turn 완료 후 비동기 sidecar agent`로 두는 쪽이 더 안전하다.

### 권장하지 않는 방식

- `research_team`, `writing_team`, `vision_team`과 같은 동급의 새 `memory_team`을 head supervisor 멤버로 추가
- 모든 사용자 turn에서 memory extraction을 위해 추가 라우팅/LLM hop을 강제

이 방식은 다음 문제가 크다.

- user-facing latency 증가
- planner/supervisor routing 복잡도 증가
- memory write 실패가 본 응답 실패로 전파될 위험
- memory persistence라는 부수효과를 본문 답변 생성과 과도하게 결합

### 권장 방식

- `memory_agent` 또는 `memory_extractor`를 `비동기 sidecar`로 둔다.
- trigger는 아래 둘 중 하나로 제한한다.
  - turn 완료 직후
  - 사용자 메시지 저장 직후의 background task
- main chat path는 memory read만 수행하고, memory write는 background에서 eventual consistency로 처리한다.
- 기본 계약은 `사용자 turn당 memory agent 1회 평가`다.
- 즉, 각 사용자 질의가 들어올 때마다 main answer 생성과 분리된 sidecar가 해당 turn을 한 번 훑고, `저장` 또는 `no-op`를 판단한다.
- 선호도/성향/지속 목표 신호가 없으면 후보를 만들지 않고 그대로 종료한다.

### 권장 파이프라인

1. `/api/chat` 또는 `/api/chat/resume`가 turn을 마무리한다.
2. background job enqueue 또는 비동기 task trigger를 건다.
3. `memory_agent`는 아래 입력만 받는다.
   - latest user message
   - 필요 시 latest assistant final answer
   - 현재 active explicit memory snapshot
4. agent는 구조화 출력으로 `memory candidates`만 생성한다.
5. rule-based guard가 allowlist/blocklist, confidence, dedupe/merge를 적용한다.
6. 통과한 후보만 `user_memory_entries`에 upsert 또는 soft-merge한다.

### 저장 판정 기본 규칙

- 선호도/성향/지속 목표 신호 없음
  - `no-op`
- 신호는 있으나 allowlist category 아님
  - `no-op`
- 신호는 있으나 confidence threshold 미달
  - `no-op`
- 민감정보 또는 금지 category
  - `no-op`
- 기존 memory와 사실상 동일
  - `merge` 또는 `no-op`
- 위 조건을 통과한 명시적 선호/성향 후보만 저장
  - `upsert`

### agent 책임 범위

- 사용자의 선호도/성향/반복 목표 후보 추출
- category classification
- confidence scoring
- 기존 memory와의 merge suggestion

### agent가 하면 안 되는 일

- main answer routing 결정
- 사용자-facing final answer 생성
- 도구 실행 권한이 큰 작업
- 승인 없는 민감정보 저장

### 구현 형태

초기 구현은 전용 팀보다 아래가 낫다.

- prompt-kit에 `MEMORY_EXTRACTOR_PROMPT` 추가
- `langchain.agents.create_agent` 기반의 좁은 범위 `memory_agent` 생성
- 별도 graph team이 아니라 service layer에서 호출
- 실패해도 본 turn은 성공 처리되는 fire-and-observe 구조

## 엄격 성능 검증 원칙

memory 기능은 정확도만 맞으면 끝나는 작업이 아니다. 다음을 release gate로 취급한다.

- 응답 품질 회귀가 없어야 한다.
- synchronous memory read가 TTFT/latency를 눈에 띄게 악화시키지 않아야 한다.
- memory write는 비동기여도 DB contention과 queue 적체를 만들지 않아야 한다.
- settings list/delete UI는 memory row가 많아져도 체감 성능이 무너지지 않아야 한다.

### 핵심 성능 가설

- read path는 매 turn 동기 경로이므로 가장 위험하다.
- write path는 sidecar로 빼면 latency 영향은 줄지만, DB write burst와 job backlog 위험이 생긴다.
- inferred memory가 늘수록 retrieval query와 prompt injection payload가 비대해질 수 있다.

### 성능 게이트

절대값과 baseline 대비 상대값을 함께 본다. baseline은 memory 기능 비활성 상태를 기준으로 측정한다.

- `chat TTFT`
  - memory enabled 시 p95가 baseline 대비 10% 이상 악화되면 실패
- `chat total latency`
  - memory enabled 시 p95가 baseline 대비 15% 이상 악화되면 실패
- `memory retrieval`
  - active memory 500건 기준 p95가 150ms를 넘으면 실패
- `settings personal memory list API`
  - 첫 페이지 50건 조회 p95가 200ms를 넘으면 실패
- `memory delete API`
  - p95가 150ms를 넘으면 실패
- `sidecar enqueue`
  - main turn finalize 직후 enqueue 오버헤드 p95가 30ms를 넘으면 실패
- `memory agent completion`
  - background completion p95가 5s를 넘으면 경고, 10s를 넘으면 실패

### 필수 성능 시나리오

- memory off baseline
- memory on, active explicit memory 10건
- memory on, active memory 100건
- memory on, active memory 500건
- concurrent chat turns + concurrent memory writes
- settings list/delete while chat traffic 동시 발생
- repeated delete/create로 tombstone이 쌓인 상태

### 필수 측정 항목

- turn p50/p95 TTFT
- turn p50/p95 total latency
- memory retrieval latency
- memory extraction latency
- DB query count per turn
- prompt injection token 증가량
- row count 증가에 따른 list/delete API latency
- background job backlog depth

### 필수 검증 방식

- unit micro-benchmark
  - retrieval selector, formatter, merge logic
- service benchmark
  - retrieval service with synthetic memory fixtures
- API benchmark
  - list/create/delete/settings endpoints
- integration benchmark
  - `/api/chat` with memory off/on 비교
- load test
  - concurrent users, concurrent turns, concurrent sidecar writes
- DB inspection
  - index hit, `EXPLAIN ANALYZE`, lock contention

## 예상 변경 지점

- 프런트 route/layout
  - 신규 `apps/frontend/src/app/settings/`
  - 신규 `apps/frontend/src/app/settings/profile/`
  - 신규 `apps/frontend/src/app/settings/personal-memory/`
- 프런트 공용 컴포넌트
  - `apps/frontend/src/components/workspace/WorkspaceTopNav.tsx`
  - `apps/frontend/src/components/workspace/AccountDrawer.tsx`
  - 신규 `apps/frontend/src/components/settings/`
  - `apps/frontend/src/components/auth/ProfilePanel.tsx`
  - 신규 password form component
- 프런트 API/types
  - `apps/frontend/src/lib/api.ts`
  - 신규 `apps/frontend/src/types/memory.ts`
- 백엔드 모델/서비스/API
  - 신규 `apps/backend/models/user_memory.py`
  - 신규 `apps/backend/models/memory_job.py` 또는 동등 job 모델
  - `apps/backend/models/__init__.py`
  - 신규 `apps/backend/services/memory_service.py`
  - 신규 `apps/backend/services/memory_agent_service.py`
  - 신규 `apps/backend/services/memory_job_service.py`
  - 신규 `apps/backend/api/routes/memory.py`
  - `apps/backend/api/routes/chat.py`
  - `apps/backend/api/routes/users.py`
  - `apps/backend/main.py`
  - `apps/backend/services/schema_patch_service.py`
- 오케스트레이션/prompt
  - `packages/agent-core/src/agent_core/state.py`
  - `packages/agent-core/src/agent_core/supervisor.py`
  - 필요 시 `packages/agent-core/src/agent_core/nodes/finalizer.py`
  - `packages/prompt-kit/src/prompt_kit/prompts.py`
- 성능 검증 자산
  - 신규 `apps/backend/tests/perf/`
  - 필요 시 `infra/scripts/` 아래 benchmark/load-test helper

## Phase 0. Design Contract Freeze

- [ ] Figma node `96:2`와 `98:183`을 settings 구현 기준 노드로 문서에 고정한다.
- [ ] settings는 전용 route로 구현하고 drawer는 보조 진입점만 유지할지 결정한다.
- [ ] `WorkspaceTopNav`를 settings에서도 재사용하고 좌측 정렬을 유지하는 원칙을 고정한다.
- [ ] settings route structure를 `/settings/profile`, `/settings/personal-memory`로 확정할지 결정한다.
- [ ] personal memory card hover `...` interaction의 기준 컴포넌트를 `ThreadListItem` 패턴으로 고정한다.
- [ ] 저장일 카피 형식을 `YYYY년 MM월 DD일에 저장되었음`으로 고정한다.
- [ ] KST 적재와 KST 표시가 모두 필요하다는 요구사항을 계약으로 고정한다.
- [ ] `Change Password`를 settings profile의 독립 섹션으로 취급하는 원칙을 고정한다.
- [ ] memory write는 head supervisor routing이 아니라 sidecar agent로 처리하는 방향을 원칙으로 고정한다.
- [ ] 성능 게이트를 release blocker로 취급하는 원칙을 고정한다.

## Phase 1. Settings Shell And Navigation Foundation

- [ ] `WorkspaceTopNavSection`에 `settings`를 추가한다.
- [ ] 기존 disabled `Settings` 버튼을 실제 route navigation으로 연결한다.
- [ ] chat/dashboard/settings가 같은 좌측 정렬 top nav layout을 공유하도록 공통 계약을 만든다.
- [ ] 신규 settings layout/page shell을 만든다.
- [ ] settings 내부 section navigation을 구현한다.
- [ ] desktop/mobile 반응형 구조를 정한다.
- [ ] `AccountDrawer`는 “즉시 편집 surface”가 아니라 settings 진입/계정 shortcut 역할로 축소할지 결정한다.
- [ ] settings route auth guard와 loading state를 정리한다.
- [ ] top nav navigation 및 settings route smoke test를 추가한다.

## Phase 2. Settings-Profile And Password Surface

- [ ] 기존 `ProfilePanel`을 settings page에 맞는 section component로 재구성한다.
- [ ] display name/email 편집을 settings profile에 배치한다.
- [ ] change password용 독립 section/card를 추가한다.
- [ ] bootstrap 강제 변경 흐름과 settings password UI가 공유할 form component를 추출한다.
- [ ] settings용 password form에 `새 비밀번호 확인` 필드를 추가한다.
- [ ] 비밀번호 규칙, inline validation, submit disable 조건을 정리한다.
- [ ] success/error/loading UX를 설계한다.
- [ ] must-change-password 전용 auth scaffold와 settings password section 간 중복 스타일/로직을 정리한다.
- [ ] 관련 frontend tests와 backend password API regression tests를 추가한다.

## Phase 3. Personal Memory Data Foundation

- [ ] `user_memory_settings` 모델을 추가한다.
- [ ] `user_memory_entries` 모델을 추가한다.
- [ ] `memory_reference_events` 모델을 추가한다.
- [ ] 필요 시 `memory_jobs` 또는 동등한 background job 추적 모델을 추가한다.
- [ ] `created_at`, `updated_at`, `deleted_at`에 KST-aware 적재 규칙을 적용한다.
- [ ] `apps/backend/models/__init__.py`에 신규 모델을 등록한다.
- [ ] startup schema patch 또는 index patch가 필요하면 `SchemaPatchService`에 추가한다.
- [ ] memory schema를 `apps/backend/schemas/`에 추가한다.
- [ ] `MemoryService`를 만들어 list/create/delete/settings update를 제공한다.
- [ ] `/api/users/me/memory/settings`와 `/api/users/me/memory` 계열 엔드포인트를 추가한다.
- [ ] soft delete/tombstone 정책을 정해 삭제 후 재생성 억제를 준비한다.
- [ ] retrieval/list/delete 성능을 위한 index 설계를 확정한다.
- [ ] backend unit/service/API tests를 추가한다.

## Phase 4. Settings-PersonalMemory UI And Interaction

- [ ] `Settings-PersonalMemory` 전용 page/section component를 만든다.
- [ ] memory list, empty state, loading state, error state를 구현한다.
- [ ] 각 memory card에 hover/focus 기반 `...` 버튼을 구현한다.
- [ ] `...` 메뉴에는 최소 `삭제` 액션을 넣는다.
- [ ] `...` 메뉴 또는 card expanded area 하단에 저장일 상태 설명을 보여준다.
- [ ] 저장일 문구는 `created_at`을 `Asia/Seoul` 기준으로 포맷한다.
- [ ] 메뉴 열림 상태, keyboard navigation, outside click close를 구현한다.
- [ ] interaction은 `ThreadListItem`과 시각/행동 일관성을 갖되, metadata 문구 영역은 settings용으로 확장한다.
- [ ] 삭제 후 optimistic UI와 rollback 정책을 정한다.
- [ ] personal memory UI tests를 추가한다.

## Phase 5. Memory Agent Sidecar Pipeline

- [ ] `MEMORY_EXTRACTOR_PROMPT`를 `packages/prompt-kit`에 추가한다.
- [ ] 전용 `memory_agent` 생성 경로를 서비스 레이어에 추가한다.
- [ ] memory agent 입력을 latest user message 중심의 좁은 payload로 제한한다.
- [ ] memory agent가 `사용자 turn당 최대 1회` 평가되도록 invocation contract를 고정한다.
- [ ] memory agent 출력은 structured candidates만 반환하게 한다.
- [ ] allowlist/blocklist guard를 agent 출력 뒤에 적용한다.
- [ ] 기존 memory와 dedupe/merge하는 policy를 구현한다.
- [ ] memory write 실패가 main turn 실패로 전파되지 않도록 isolation 계약을 추가한다.
- [ ] sidecar enqueue와 completion을 trace/log로 관찰 가능하게 만든다.
- [ ] background retry, dead-letter 또는 equivalent failure policy를 정한다.
- [ ] memory agent accuracy tests와 failure-isolation tests를 추가한다.

## Phase 6. Runtime Memory Retrieval Integration

- [ ] turn 시작 전에 memory를 읽는 `MemoryRetrievalService`를 추가한다.
- [ ] retrieval 결과를 `shared_context.personalization`에 주입한다.
- [ ] `/api/chat`와 `/api/chat/resume`가 동일한 memory read 규칙을 사용하게 한다.
- [ ] prompt-kit에 memory usage 규칙용 prompt block/template를 추가한다.
- [ ] supervisor가 memory를 routing 보조 컨텍스트로만 쓰도록 제한한다.
- [ ] finalizer/writing 경로가 language/tone/format preference를 활용하도록 프롬프트를 보강한다.
- [ ] retrieval된 memory를 `memory_reference_events`에 기록한다.
- [ ] trace/debug payload에 memory hit count와 reference id를 남긴다.
- [ ] memory가 없거나 비활성화된 경우 기존 동작이 유지되는 회귀 테스트를 추가한다.

## Phase 7. Temporary Chat, Inferred Memory, Rollout

- [ ] `ChatRequest`와 `ResumeRequest`에 memory mode 필드를 추가한다.
- [ ] temporary mode에서는 memory read/write를 모두 차단한다.
- [ ] settings에서 memory enable/disable과 inferred memory enable/disable을 제어할 수 있게 한다.
- [ ] turn 완료 후 inferred memory candidate를 추출하는 lightweight extractor를 추가한다.
- [ ] inferred memory는 allowlist category만 생성하게 한다.
- [ ] explicit memory와 inferred memory 충돌 시 explicit를 우선한다.
- [ ] 삭제된 memory가 바로 재생성되지 않도록 suppression/tombstone 정책을 적용한다.
- [ ] feature flag 또는 staged rollout 정책을 추가한다.
- [ ] 관련 backend/frontend/manual regression을 추가한다.

## Phase 8. Performance Validation And Release Gate

- [ ] memory off baseline benchmark를 먼저 측정한다.
- [ ] memory on 상태에서 10/100/500 active memory fixture benchmark를 측정한다.
- [ ] retrieval service p50/p95 benchmark를 추가한다.
- [ ] settings personal memory list/delete API benchmark를 추가한다.
- [ ] `/api/chat` TTFT/latency 비교 benchmark를 추가한다.
- [ ] memory agent enqueue 및 completion latency benchmark를 추가한다.
- [ ] concurrent chat + concurrent sidecar write load test를 추가한다.
- [ ] tombstone 누적 상태에서 retrieval/list 성능 저하를 측정한다.
- [ ] query plan과 index hit를 `EXPLAIN ANALYZE`로 검증한다.
- [ ] 성능 게이트 초과 시 rollout 중단 규칙을 문서화한다.

## 검증 방법

### 백엔드

- [ ] `cd apps/backend && uv run pytest tests/ -v`
- [ ] memory CRUD, KST timestamps, soft delete, retrieval, temporary chat, inferred write-back을 각각 검증한다.
- [ ] password change API regression이 유지되는지 확인한다.
- [ ] perf fixture 기반 retrieval/list/delete benchmark를 실행한다.
- [ ] memory on/off chat integration benchmark를 실행한다.

### 프런트엔드

- [ ] `cd apps/frontend && npm run test`
- [ ] `cd apps/frontend && npm run lint`
- [ ] `cd apps/frontend && npm run build`
- [ ] top nav 좌측 정렬과 settings navigation 회귀가 없는지 확인한다.
- [ ] personal memory `...` hover/focus interaction을 test로 고정한다.

### 성능/부하

- [ ] benchmark/load-test 스크립트를 실행한다.
- [ ] p50/p95 TTFT와 latency가 게이트 이내인지 확인한다.
- [ ] list/delete API가 row count 증가에도 게이트를 만족하는지 확인한다.
- [ ] concurrent sidecar writes에서 DB lock contention이 없는지 확인한다.

### 정합성 통합 테스트

- [ ] 선호도 신호가 포함된 질의 후 memory agent가 정확히 1회 실행되는지 검증한다.
- [ ] 예시 질의 `난 가수 백예린을 굉장히 좋아해. 그녀의 대표곡 5개만 뽑아줘.` 이후 memory candidate가 생성되는지 검증한다.
- [ ] 위 시나리오에서 저장 결과가 예: `{USER}는 가수 백예린을 좋아한다.` 형태의 allowlist category로 정규화되는지 검증한다.
- [ ] 위 시나리오에서 `user_memory_entries.created_at`가 KST 기준으로 적재되는지 검증한다.
- [ ] 위 시나리오에서 settings personal memory UI가 `YYYY년 MM월 DD일에 저장되었음` 문구를 정확히 표시하는지 검증한다.
- [ ] 선호도 신호가 없는 질의 예: `백예린 대표곡 5개만 뽑아줘.` 에서는 memory agent가 `no-op`로 끝나고 DB write가 0건인지 검증한다.
- [ ] 일회성 요청 예: `오늘만 3문장 이하로 답해줘.` 는 global personal memory로 저장되지 않는지 검증한다.
- [ ] 민감정보 포함 질의는 candidate가 생성되더라도 최종 저장이 차단되는지 검증한다.
- [ ] 동일 선호가 반복 입력될 때 duplicate row를 추가하지 않고 merge 또는 no-op가 되는지 검증한다.
- [ ] memory delete 후 동일 질의가 재입력되지 않은 상태에서는 tombstone/suppression 때문에 즉시 재생성되지 않는지 검증한다.
- [ ] memory agent 실패 또는 timeout이 나도 main chat answer는 정상 완료되고 turn status가 실패로 오염되지 않는지 검증한다.
- [ ] `/api/chat/resume` 경로에서도 동일한 memory extraction/no-op 규칙이 유지되는지 검증한다.

### 수동 시나리오

- [ ] chat 화면과 settings 화면의 top nav가 모두 좌측 정렬 레이아웃인지 확인한다.
- [ ] settings profile에서 display name/email 수정이 정상 반영되는지 확인한다.
- [ ] settings profile의 change password가 성공/실패/validation 상태를 올바르게 표시하는지 확인한다.
- [ ] personal memory card hover 시 `...`가 나타나는지 확인한다.
- [ ] `...` 클릭 시 `삭제`와 저장일 상태 문구가 보이는지 확인한다.
- [ ] 저장일 문구가 실제 KST 기준 날짜와 일치하는지 확인한다.
- [ ] temporary chat에서는 memory가 read/write되지 않는지 확인한다.
- [ ] explicit memory 저장 후 새 thread 응답에 반영되는지 확인한다.
- [ ] 사용자의 선호 문장이 포함된 질의 후 background memory agent가 후보를 적재하는지 확인한다.
- [ ] 선호 문장이 없는 질의 후에는 background memory agent가 DB에 아무것도 적재하지 않는지 확인한다.
- [ ] memory agent 실패 상황에서도 사용자 응답이 정상 완료되는지 확인한다.

## 완료 조건

- settings는 전용 route와 shell을 가진다.
- settings의 top nav는 chat/dashboard와 동일한 좌측 정렬 구조를 유지한다.
- `Settings-Profile`에는 profile edit와 change password가 분리된 중요 섹션으로 존재한다.
- `Settings-PersonalMemory`의 각 memory card는 hover `...` interaction, 삭제 액션, 저장일 상태 문구를 제공한다.
- `user_memory_entries`는 KST 기준 `created_at`을 적재한다.
- memory 추출은 sidecar agent 또는 동등한 비동기 파이프라인으로 처리되며, main chat critical path를 오염시키지 않는다.
- `/api/chat`와 `/api/chat/resume`는 settings memory 정책에 따라 personalization context를 일관되게 주입한다.
- temporary chat에서는 memory read/write가 모두 차단된다.
- memory enabled 상태에서도 TTFT/latency가 정의된 성능 게이트를 넘지 않는다.
- memory reference가 traceable하며, 문제 응답이 나왔을 때 어떤 memory가 사용됐는지 역추적할 수 있다.
