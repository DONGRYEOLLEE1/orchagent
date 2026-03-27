---
작업명: Chat Thread URL Routing Plan
간단요약: 채팅 워크스페이스를 `/` 드래프트와 `/c/{threadId}` 구조로 분리하되, persistent workspace host를 도입해 live stream과 route 전환이 충돌하지 않도록 리팩토링한다.
작성일시: 2026-03-27 16:27 KST
최종 수정일시: 2026-03-27 23:58 KST
---

# Chat Thread URL Routing 리팩토링 계획

## 목표

- 현재 `localhost:3000/` 단일 경로에 머무르는 채팅 워크스페이스를 `draft`와 `saved thread`로 분리한다.
- URL이 현재 active thread의 source of truth 역할을 하도록 바꾼다.
- 새로고침, 뒤로가기/앞으로가기, 멀티탭, 링크 복사/공유 시 thread 복원이 자연스럽게 동작하도록 만든다.
- route 전환 시 live stream, reasoning, tool strip, suggested queries 상태가 끊기거나 누수되지 않게 만든다.

## 적용 가능성 판정

- 판정: `조건부 적용 가능`
- 적용 가능 근거:
  - backend는 이미 `fetchThreadDetail(threadId)`, `fetchThreadTelemetry(threadId)`, `deleteThread(threadId)`를 제공한다.
  - 클라이언트는 이미 optimistic `thread_${Date.now()}` id를 생성해 turn을 시작할 수 있다.
- 현재 그대로 구현하면 위험한 이유:
  - live stream/SSE reader와 optimistic message append 상태가 현재 [WorkspaceRouteRoot.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx)에 집중되어 있다.
  - `/`와 `/c/[threadId]`를 별도 page로 단순 분리하면 route 전환 시 `WorkspaceApp` remount가 발생할 수 있고, 그 순간 live turn이 끊길 가능성이 높다.
- 결론:
  - `page 분리` 자체는 가능하다.
  - 단, 그 전에 `route transition 중에도 살아남는 persistent workspace host/layout`를 먼저 도입해야 한다.

## 최종 URL 계약

- `/`
  - 새 대화 초안 상태
  - active thread가 아직 없는 상태
- `/c/{threadId}`
  - 특정 thread를 보는 상태
  - detail/telemetry fetch 기준 경로

## 기대 효과

- 새로고침 후 같은 대화가 그대로 복원됨
- 브라우저 뒤로가기/앞으로가기가 thread 탐색과 일치함
- 서로 다른 thread를 탭별로 동시에 열 수 있음
- “현재 어떤 대화인지”가 URL만으로 식별됨
- 디버깅/재현/운영 커뮤니케이션이 쉬워짐

## 현재 구조 요약

- 메인 채팅 화면은 현재 [WorkspaceRouteRoot.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx)에 몰려 있다.
- 현재 active thread는 `activeThreadState.threadId`와 local state로만 관리된다.
- thread click은 `handleSelectThread()`에서 detail fetch 후 local state를 바꾼다.
- 새 chat은 `handleStartNewChat()`이 local state만 초기화한다.
- 첫 질문 전송 시 client가 `thread_${Date.now()}`로 optimistic thread id를 만들고 backend로 보낸다.
- `sendChatStream()` 및 `resumeChatStream()`의 실제 SSE 처리 루프도 같은 컴포넌트 내부에 있다.

즉 현재는 `URL`이 아니라 `client memory`가 active thread의 기준이고, route 전환에 취약한 구조다.

## 설계 결론

### 1. URL을 source of truth로 승격

- active thread는 `pathname` 기준으로 결정한다.
- `/`면 draft
- `/c/{threadId}`면 saved thread

### 2. 페이지 구조는 `분리 + persistent host`가 전제

권장 구조:

- `app/(workspace)/layout.tsx`
  - auth gate + persistent `WorkspaceHost` 유지
  - `/`와 `/c/[threadId]` 사이 이동 시 remount되지 않는 상위 layout
- `app/(workspace)/page.tsx`
  - draft entry
- `app/(workspace)/c/[threadId]/page.tsx`
  - saved thread entry
- 공통 UI는 `ChatWorkspaceShell` 같은 순수 렌더 컴포넌트로 추출
- route param 해석, thread hydration, stream lifecycle은 `WorkspaceHost`가 담당

비권장 구조:

- `app/page.tsx`와 `app/c/[threadId]/page.tsx`를 각각 독립 client page로 두고 상태를 각 페이지 내부에 저장하는 방식
  - 이유: route 전환 시 remount 가능성이 커서 live turn이 끊길 수 있다.

### 3. 라우팅 정책

- sidebar thread click:
  - `router.push('/c/{threadId}')`
- `New Chat`:
  - `router.push('/')`
- 첫 질문 전송:
  - optimistic thread id는 기존처럼 즉시 생성
  - 단, URL 전환은 `sendChatStream()`이 성공적으로 `ReadableStream`을 반환한 직후 `router.replace('/c/{threadId}')`
  - 즉, `thread id 생성 직후`가 아니라 `서버가 turn을 수락한 직후` URL 전환
- 삭제:
  - 현재 thread 삭제 시 `router.replace('/')`
- 존재하지 않는 thread:
  - 404 page보다는 `router.replace('/')` + workspace inline error banner가 더 실용적
  - 현재 toast 인프라가 없으므로 초기 버전은 toast 대신 inline error를 사용

### 4. 상태 정책

- route param 변경 시 thread detail/telemetry를 다시 hydrate
- `activeThreadState`는 여전히 필요하지만 URL에서 유도되는 상태로 취급
- URL과 local state가 어긋나는 직접 mutation을 금지
- `handleSelectThread()`와 `handleStartNewChat()`은 더 이상 직접 fetch/reset을 책임지지 않고, route 변경만 담당하는 얇은 함수가 된다.
- 실제 reset/hydration은 `routeThreadId`를 감시하는 effect 하나로 수렴시킨다.

### 5. draft와 historical/live 구분 유지

- `/`
  - `viewMode='draft'`
- `/c/{threadId}`
  - 저장된 thread open 시 `historical`
  - 현재 진행 중이면 `live`

## 범위

포함:

- frontend app router 리팩토링
- persistent workspace host/layout 추출
- shared chat workspace shell 추출
- route-driven thread hydration
- new chat/select thread/delete thread/send flow 수정
- 관련 테스트 보강

비포함:

- backend API 구조 변경
- thread ownership 정책 변경
- settings/dashboard 경로 변경

## 전제

- backend는 이미 `fetchThreadDetail(threadId)`와 `fetchThreadTelemetry(threadId)`를 제공한다.
- thread id는 client-generated optimistic id를 이미 사용한다.
- 단, route 전환 시점은 `sendChatStream()` 성공 후로 미뤄 서버가 turn을 수락했다는 사실을 확보한다.
- 현재 auth 흐름은 유지하고, 미로그인 시 여전히 `/login`으로 보낸다.
- route 전환 중에도 live stream state가 살아남아야 하므로, `WorkspaceHost`는 route page보다 상위 layout에서 유지되어야 한다.

## 주요 리스크와 대응

### 리스크 1. `/` -> `/c/{threadId}` 전환 시 live stream 끊김

- 원인:
  - 현재 stream reader와 local state가 [WorkspaceRouteRoot.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx)에 집중되어 있다.
- 대응:
  - route group layout 아래에 persistent `WorkspaceHost`를 두고, 실제 page는 route param만 전달하는 thin entry로 제한한다.

### 리스크 2. 첫 turn 실패 시 유효하지 않은 `/c/{threadId}` URL 잔존

- 원인:
  - optimistic thread id는 클라이언트가 먼저 만들지만, 서버가 아직 turn을 수락하지 않았을 수 있다.
- 대응:
  - `sendChatStream()`이 성공적으로 response body를 반환한 뒤에만 `router.replace('/c/{threadId}')`
  - upload/send 실패가 이 단계 이전에 발생하면 URL은 `/` 유지

### 리스크 3. invalid thread 진입 정책 부재

- 원인:
  - 기존 초안은 toast/error state라고만 적혀 있고, 현재 프로젝트에 toast 인프라가 없다.
- 대응:
  - 1차 릴리스는 `/` fallback + inline error banner
  - toast 도입은 별도 작업으로 분리

### 리스크 4. route 전환 시 telemetry/reasoning/tool strip 누수

- 원인:
  - 현재 `actionSpaceState` reset과 historical telemetry hydrate가 여러 함수에 분산돼 있다.
- 대응:
  - `routeThreadId` 단일 effect에서 reset/hydration 정책을 명시
  - pending request id ref 정리도 같은 effect에서 수행

## Phase 1. Persistent Workspace Host 추출

- [x] 기존 메인 채팅 엔트리의 live stream state, thread collection state, action space state를 `WorkspaceHost` 역할의 [WorkspaceRouteRoot.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx)로 이동
- [x] `WorkspaceHost`가 `routeThreadId | null`과 auth/logout 의존성만 받게 정리
- [x] route group layout 아래에서 `WorkspaceHost`가 remount되지 않는 구조로 배치
- [x] 관련 테스트 통과 확인

## Phase 2. Shared Workspace Shell 및 Route Entry 분리

- [x] shared route root와 thin route entry 구조로 분리
- [x] `app/(workspace)/page.tsx`는 `routeThreadId = null` entry만 담당
- [x] `app/(workspace)/c/[threadId]/page.tsx`는 `routeThreadId` 전달만 담당
- [x] layout/auth redirect와 충돌 없는지 확인
- [x] 관련 테스트 통과 확인

## Phase 3. Route-driven Hydration

- [x] `routeThreadId` 변경 시 `fetchThreadDetail + fetchThreadTelemetry`가 동작하도록 단일 effect 정리
- [x] 기존 `handleSelectThread()` 흐름을 `router.push('/c/{threadId}')` 기반으로 전환하고, 클릭 즉시 hydrate도 유지하는 하이브리드로 안정화
- [x] 기존 `handleStartNewChat()` 흐름을 `router.push('/')` 기반으로 전환
- [x] 같은 thread 재선택 시 중복 fetch 방지
- [x] invalid/missing thread일 때 `/` fallback + inline error banner 정책 적용
- [x] 관련 테스트 통과 확인

## Phase 4. Send / New Chat / Delete 흐름 정리

- [x] 첫 user turn에서 `sendChatStream()` 성공 직후 `router.replace('/c/{threadId}')`
- [x] upload 실패 또는 stream 시작 전 요청 실패 시 `/`에 남는 rollback 정책 반영
- [x] `New Chat`은 local reset과 함께 `/`로 push
- [x] 현재 보고 있는 thread 삭제 시 `/`로 replace
- [x] rename/pin/suggested-queries/title-refresh가 route state와 충돌하지 않도록 조정
- [x] resume/HITL 흐름이 `/c/{threadId}`에서 유지되는지 확인
- [x] 관련 테스트 통과 확인

## Phase 5. Browser Navigation Semantics

- [x] 뒤로가기/앞으로가기 시 thread state가 정상 복원되는지 확인
- [x] 탭 여러 개에서 서로 다른 `/c/{threadId}`를 열었을 때 독립 동작 확인
- [x] 새로고침 시 active thread 복원 확인
- [x] copy-paste된 `/c/{threadId}` 링크 직접 진입 확인

## Phase 6. UX Hardening

- [x] active thread가 없는 `/`에서 빈 상태 UI 유지
- [x] loading skeleton과 `detailLoadState` 전환이 route 기반으로 자연스러운지 점검
- [x] historical/live/action panel 상태가 route 전환 시 누수되지 않게 정리
- [x] telemetry/reasoning/suggested queries가 thread 전환 시 섞이지 않도록 보강
- [x] `/c/{threadId}`에서 새로고침했을 때 thread detail hydrate 전에 이전 draft 흔적이 비치지 않도록 초기 loading guard 보강

## Phase 7. 테스트 계획

- [x] thread click 시 `/c/{threadId}` 이동 테스트
- [x] `New Chat` 시 `/` 복귀 테스트
- [x] 첫 전송에서 `sendChatStream()` 성공 후 `/c/{threadId}` replace 테스트
- [x] 첫 전송에서 stream 시작 전 실패하면 `/` 유지 테스트
- [x] 새로고침/직접 진입 `/c/{threadId}` hydration 테스트
- [x] 삭제 후 `/` fallback 테스트
- [x] 뒤로가기/앞으로가기 내비게이션 테스트
- [x] `historical -> live -> historical` 전환 회귀 테스트

## Phase 8. 출시 전 검증

- [x] `npm run test`
- [x] `npm run lint`
- [x] `npm run build`
- [x] 브라우저 수동 검증
  - [x] `/`에서 새 대화 시작 후 `/c/{threadId}` 전환 확인
  - [x] 기존 thread 클릭 시 URL 변경 확인
  - [x] 새로고침 후 동일 thread 복원 확인
  - [x] 삭제 후 `/` 복귀 확인
  - [x] 뒤로가기/앞으로가기 확인
  - [x] 첫 전송 실패 시 URL이 `/`에 남는지 확인

## 구현 원칙

- URL과 local state 중 하나만 진실이어야 한다. 여기서는 URL이 진실이다.
- 기존 shell UI와 디자인은 보존하고, 라우팅 책임만 분리한다.
- optimistic thread id를 이미 쓰지만, URL 전환은 `sendChatStream()` 성공 후에만 수행한다.
- route transition 중 state 누수를 막기 위해 `createInitial*State()` reset 시점을 명확히 한다.
- `/`와 `/c/[threadId]` 사이 이동 시 live stream을 유지해야 하므로, route page보다 상위의 persistent layout/provider를 전제로 한다.

## 참고 파일

- [WorkspaceRouteRoot.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx)
- [workspace-state.ts](/Users/drlee/workspace/orchagent/apps/frontend/src/lib/workspace-state.ts)
- [ThreadListSidebar.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/sidebar/ThreadListSidebar.tsx)
- [ThreadListItem.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/sidebar/ThreadListItem.tsx)
