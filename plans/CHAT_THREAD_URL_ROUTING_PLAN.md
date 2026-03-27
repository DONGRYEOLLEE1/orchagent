---
작업명: Chat Thread URL Routing Plan
간단요약: 채팅 워크스페이스를 `/` 드래프트와 `/c/{threadId}` 스레드 URL 구조로 분리해 복원성, 링크 공유성, 브라우저 내비게이션 일관성을 높인다.
작성일시: 2026-03-27 16:27 KST
최종 수정일시: 2026-03-27 16:27 KST
---

# Chat Thread URL Routing 리팩토링 계획

## 목표

- 현재 `localhost:3000/` 단일 경로에 머무르는 채팅 워크스페이스를 `draft`와 `saved thread`로 분리한다.
- URL이 현재 active thread의 source of truth 역할을 하도록 바꾼다.
- 새로고침, 뒤로가기/앞으로가기, 멀티탭, 링크 복사/공유 시 thread 복원이 자연스럽게 동작하도록 만든다.

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

- 메인 채팅 화면은 [page.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/app/page.tsx)에 몰려 있다.
- 현재 active thread는 `activeThreadState.threadId`와 local state로만 관리된다.
- thread click은 `handleSelectThread()`에서 detail fetch 후 local state를 바꾼다.
- 새 chat은 `handleStartNewChat()`이 local state만 초기화한다.
- 첫 질문 전송 시 client가 `thread_${Date.now()}`로 optimistic thread id를 만들고 backend로 보낸다.

즉 현재는 `URL`이 아니라 `client memory`가 active thread의 기준이다.

## 설계 결론

### 1. URL을 source of truth로 승격

- active thread는 `pathname` 기준으로 결정한다.
- `/`면 draft
- `/c/{threadId}`면 saved thread

### 2. 페이지 구조 분리

권장 구조:

- `app/page.tsx`
  - draft entry
- `app/c/[threadId]/page.tsx`
  - saved thread entry
- 공통 채팅 UI는 shared workspace component로 추출
  - 예: `components/workspace/ChatWorkspaceShell.tsx`

### 3. 라우팅 정책

- sidebar thread click:
  - `router.push('/c/{threadId}')`
- `New Chat`:
  - `router.push('/')`
- 첫 질문 전송:
  - optimistic thread id 생성 직후 `router.replace('/c/{threadId}')`
- 삭제:
  - 현재 thread 삭제 시 `router.replace('/')`
- 존재하지 않는 thread:
  - 404 대신 UX상 `/`로 보내고 toast/error state 노출이 더 실용적

### 4. 상태 정책

- route param 변경 시 thread detail/telemetry를 다시 hydrate
- `activeThreadState`는 여전히 필요하지만 URL에서 유도되는 상태로 취급
- URL과 local state가 어긋나는 직접 mutation을 금지

### 5. draft와 historical/live 구분 유지

- `/`
  - `viewMode='draft'`
- `/c/{threadId}`
  - 저장된 thread open 시 `historical`
  - 현재 진행 중이면 SSE 연결 후 `live`

## 범위

포함:

- frontend app router 리팩토링
- shared chat workspace component 추출
- route-driven thread hydration
- new chat/select thread/delete thread/send flow 수정
- 관련 테스트 보강

비포함:

- backend API 구조 변경
- thread ownership 정책 변경
- settings/dashboard 경로 변경

## 전제

- backend는 이미 `fetchThreadDetail(threadId)`와 `fetchThreadTelemetry(threadId)`를 제공한다.
- thread id는 client-generated optimistic id를 이미 사용하므로, 첫 전송 시 곧바로 `/c/{threadId}`로 갈 수 있다.
- 현재 auth 흐름은 유지하고, 미로그인 시 여전히 `/login`으로 보낸다.

## Phase 1. Shared Workspace Shell 추출

- [ ] 현재 [page.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/app/page.tsx)에서 라우팅과 무관한 chat workspace UI를 공통 컴포넌트로 분리
- [ ] 공통 shell이 `routeThreadId | null`을 받게 설계
- [ ] `/`와 `/c/[threadId]`에서 같은 shell을 재사용하도록 구조화
- [ ] 관련 테스트 통과 확인

## Phase 2. `/c/[threadId]` Route 도입

- [ ] `app/c/[threadId]/page.tsx` 추가
- [ ] route param을 shell에 주입
- [ ] `/` route는 `routeThreadId = null`로 shell 호출
- [ ] layout/auth redirect와 충돌 없는지 확인
- [ ] 관련 테스트 통과 확인

## Phase 3. Route-driven Hydration

- [ ] route param 변경 시 `fetchThreadDetail + fetchThreadTelemetry`가 동작하도록 effect 정리
- [ ] 기존 `handleSelectThread()`의 local-state-only 흐름을 route push 기반으로 전환
- [ ] 같은 thread 재선택 시 중복 fetch 방지
- [ ] invalid/missing thread일 때 `/` fallback 또는 명확한 에러 정책 적용
- [ ] 관련 테스트 통과 확인

## Phase 4. Send / New Chat / Delete 흐름 정리

- [ ] 첫 user turn 전송 직후 `router.replace('/c/{threadId}')`
- [ ] `New Chat`은 `/`로 push
- [ ] 현재 보고 있는 thread 삭제 시 `/`로 replace
- [ ] rename/pin/suggested-queries/title-refresh가 route state와 충돌하지 않도록 조정
- [ ] resume/HITL 흐름이 `/c/{threadId}`에서 유지되는지 확인
- [ ] 관련 테스트 통과 확인

## Phase 5. Browser Navigation Semantics

- [ ] 뒤로가기/앞으로가기 시 thread state가 정상 복원되는지 확인
- [ ] 탭 여러 개에서 서로 다른 `/c/{threadId}`를 열었을 때 독립 동작 확인
- [ ] 새로고침 시 active thread 복원 확인
- [ ] copy-paste된 `/c/{threadId}` 링크 직접 진입 확인

## Phase 6. UX Hardening

- [ ] active thread가 없는 `/`에서 빈 상태 UI 유지
- [ ] loading skeleton과 `detailLoadState` 전환이 route 기반으로 자연스러운지 점검
- [ ] historical/live/action panel 상태가 route 전환 시 누수되지 않게 정리
- [ ] telemetry/ reasoning / suggested queries가 thread 전환 시 섞이지 않도록 보강

## Phase 7. 테스트 계획

- [ ] thread click 시 `/c/{threadId}` 이동 테스트
- [ ] `New Chat` 시 `/` 복귀 테스트
- [ ] 첫 전송 시 `/c/{threadId}` replace 테스트
- [ ] 새로고침/직접 진입 `/c/{threadId}` hydration 테스트
- [ ] 삭제 후 `/` fallback 테스트
- [ ] 뒤로가기/앞으로가기 내비게이션 테스트
- [ ] `historical -> live -> historical` 전환 회귀 테스트

## Phase 8. 출시 전 검증

- [ ] `npm run test`
- [ ] `npm run lint`
- [ ] `npm run build`
- [ ] 브라우저 수동 검증
  - [ ] `/`에서 새 대화 시작 후 `/c/{threadId}` 전환 확인
  - [ ] 기존 thread 클릭 시 URL 변경 확인
  - [ ] 새로고침 후 동일 thread 복원 확인
  - [ ] 삭제 후 `/` 복귀 확인
  - [ ] 뒤로가기/앞으로가기 확인

## 구현 원칙

- URL과 local state 중 하나만 진실이어야 한다. 여기서는 URL이 진실이다.
- 기존 shell UI와 디자인은 보존하고, 라우팅 책임만 분리한다.
- optimistic thread id를 이미 쓰고 있으므로, 첫 질문 직후 URL 전환은 별도 서버 round-trip을 기다릴 필요가 없다.
- route transition 중 state 누수를 막기 위해 `createInitial*State()` reset 시점을 명확히 한다.

## 참고 파일

- [page.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/app/page.tsx)
- [workspace-state.ts](/Users/drlee/workspace/orchagent/apps/frontend/src/lib/workspace-state.ts)
- [ThreadListSidebar.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/sidebar/ThreadListSidebar.tsx)
- [ThreadListItem.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/sidebar/ThreadListItem.tsx)
