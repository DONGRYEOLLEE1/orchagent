작성일시: 2026-03-24 11:55 KST
최종 수정일시: 2026-03-24 13:17 KST

# Pinned Thread Top Order Plan

목표: 사용자가 thread를 `핀 고정`하면 스레드 목록에서 항상 최상단 pinned 그룹으로 올라가고, 그 안에서는 최근 활동순이 유지되도록 정렬 정책을 서버와 프런트 양쪽에서 일관되게 맞춘다.

## 1. 문제 정의

- 현재 thread 목록은 기본적으로 최근 활동순으로만 정렬된다.
- `pinned` 값은 표시만 되고 정렬 우선권이 없다.
- 따라서 사용자가 핀을 눌러도 해당 thread가 최상단으로 올라오지 않는다.

## 2. 현재 구조 진단

### 2.1 백엔드

- `apps/backend/services/thread_service.py`
  - `ThreadService._thread_summary_stmt()`는 `last_activity_at DESC, created_at DESC` 기준으로만 정렬한다.
  - `ThreadProfileService.get_thread_profiles_map()`으로 pinned/archived 값을 붙이지만, 프로필 값을 붙인 뒤 재정렬은 하지 않는다.
- 결과적으로 `GET /api/threads`의 canonical order는 pinned 여부를 반영하지 않는다.

### 2.2 프런트엔드

- `apps/frontend/src/lib/workspace-state.ts`
  - `upsertThreadSummary()`는 항상 새/업데이트 summary를 배열 맨 앞에 넣는다.
  - pinned 여부를 고려한 stable sorting이 없다.
- `apps/frontend/src/app/page.tsx`
  - `handleTogglePinnedThread()`는 optimistic patch만 수행하고 정렬은 다시 하지 않는다.
  - `handleDeleteThread()` rollback에서만 로컬 정렬을 따로 한다.
- 결과적으로 서버 응답 전후, 새로고침 전후, optimistic state와 canonical state가 서로 다를 수 있다.

## 3. 목표 정렬 규칙

- 최우선 정렬 키: `pinned DESC`
- 2차 정렬 키: `last_activity_at DESC`
- 3차 정렬 키: `created_at DESC`

즉:

- pinned thread는 항상 unpinned thread보다 앞에 온다.
- pinned thread끼리는 최근 활동순이다.
- unpinned thread끼리도 최근 활동순이다.

## 4. 요구되는 일관성

- `GET /api/threads` 결과가 이미 pinned-top order여야 한다.
- 프런트 optimistic update도 같은 정렬 규칙을 사용해야 한다.
- 사용자가 pin/unpin 한 직후 새로고침해도 순서가 그대로 유지되어야 한다.
- thread title patch, AI title patch, chat stream preview patch 같은 다른 summary update도 pinned order를 깨면 안 된다.

## 5. 권장 구현 방향

### 권장안

- 공통 정렬 함수를 프런트와 백엔드에 각각 명시적으로 둔다.
- 백엔드:
  - profile override 적용 후 `list_thread_summaries()` 결과를 pinned-top order로 sort
- 프런트:
  - `upsertThreadSummary()`와 `patchThreadSummary()`가 항상 정렬된 배열을 반환
  - page.tsx에서 개별 optimistic patch 호출은 이 helper를 신뢰

### 이유

- 서버 canonical order와 클라이언트 optimistic order가 같아야 새로고침/재조회 시 깜빡임이 없다.
- page 컴포넌트 곳곳에서 정렬을 반복 구현하면 회귀가 쉽게 생긴다.

## 6. 상세 작업 체크리스트

### Phase 0. 정렬 계약 고정

- [x] pinned-top order를 공식 정렬 규칙으로 문서화한다.
- [x] pinned thread 내부에서는 최근 활동순을 유지한다는 정책을 고정한다.
- [x] unpinned thread 내부에서도 최근 활동순을 유지한다는 정책을 고정한다.
- [x] optimistic update와 canonical API response가 같은 정렬 규칙을 사용해야 한다는 원칙을 고정한다.

### Phase 1. 백엔드 정렬 보강

- [x] `ThreadService`에 summary 정렬용 helper를 추가한다.
- [x] helper는 `pinned`, `last_activity_at`, `created_at` 순으로 정렬한다.
- [x] `list_thread_summaries()`에서 profile override 적용 후 정렬 helper를 호출한다.
- [x] `get_thread_summary()`는 단일 row 조회이므로 정렬 영향이 없음을 확인한다.

### Phase 2. 프런트 정렬 보강

- [x] `workspace-state.ts`에 thread summary 정렬 helper를 추가한다.
- [x] `upsertThreadSummary()`가 pinned-top order를 유지하도록 수정한다.
- [x] `patchThreadSummary()`가 pinned-top order를 유지하도록 수정한다.
- [x] 필요 시 delete rollback 경로도 같은 helper를 재사용하도록 정리한다.

### Phase 3. UI 동작 검증

- [x] pin 버튼 클릭 직후 optimistic하게 최상단으로 이동하는지 확인한다.
- [x] unpin 직후 해당 thread가 최근 활동순 위치로 되돌아가는지 확인한다.
- [x] pinned thread가 여러 개일 때 그 내부 순서가 최근 활동순인지 확인한다.
- [x] pinned thread가 새 메시지를 받아도 pinned 그룹 안에서만 순서가 바뀌는지 확인한다.

### Phase 4. 테스트

- [x] backend test를 추가한다.
- [x] pinned summary가 unpinned summary보다 앞에 오는지
- [x] pinned thread끼리 최근 활동순이 유지되는지
- [x] frontend helper test를 추가한다.
- [x] `upsertThreadSummary()` pinned ordering test
- [x] `patchThreadSummary()` pinned ordering test
- [x] page interaction test를 추가한다.
- [x] pin 토글 후 최상단 이동
- [x] unpin 후 일반 정렬 복귀
- [x] 새로고침(fetchThreads 재반영) 후 순서 유지

### Phase 5. 수동 검증

- [x] thread 여러 개를 준비한다.
- [x] 중간 위치의 thread를 pin하면 즉시 최상단으로 이동하는지 확인한다.
- [x] 여러 pinned thread가 있을 때 최근 활동순 정렬이 유지되는지 확인한다.
- [x] 새로고침 후에도 pinned thread가 여전히 위에 있는지 확인한다.

## 7. 검증 체크리스트

### 자동 검증 체크리스트

- [x] backend ordering test 통과
- [x] frontend helper ordering test 통과
- [x] page interaction test 통과

### 수동 검증 체크리스트

- [x] pin 직후 최상단 이동
- [x] unpin 후 정상 위치 복귀
- [x] 새로고침 후 순서 유지

## 8. 완료 조건

- pinned thread는 항상 unpinned thread보다 위에 온다.
- pinned group 내부는 최근 활동순이다.
- optimistic UI와 API 재조회 결과의 정렬이 일치한다.
- 새로고침 후에도 pinned-top order가 유지된다.
