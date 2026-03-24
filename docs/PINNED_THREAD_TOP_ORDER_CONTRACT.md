작성일시: 2026-03-24 13:08 KST
최종 수정일시: 2026-03-24 13:08 KST

# Pinned Thread Top Order Contract

## 목표

- pinned thread는 항상 thread 목록 최상단 pinned 그룹에 배치한다.
- pinned 여부와 최근 활동순 정렬이 서버와 프런트에서 동일하게 유지되도록 한다.

## 정렬 규칙

thread summary 목록은 다음 우선순위로 정렬한다.

1. `pinned DESC`
2. `last_activity_at DESC`
3. `created_at DESC`

즉:

- pinned thread는 항상 unpinned thread보다 앞에 온다.
- pinned thread끼리는 최근 활동순을 유지한다.
- unpinned thread끼리도 최근 활동순을 유지한다.

## canonical order 계약

- `GET /api/threads`의 응답 결과 자체가 이미 pinned-top order여야 한다.
- 프런트 optimistic update도 동일한 정렬 규칙을 따라야 한다.
- 새로고침 직후와 optimistic UI 상태의 순서가 달라지면 안 된다.

## 적용 범위

- pin/unpin 토글 직후 목록 재배치
- chat stream 중 `preview`, `last_activity_at`, `latest_status` patch
- AI thread title patch
- manual rename patch
- silent refresh 이후 목록 재반영

## 경계 조건

- pin된 thread가 새 메시지를 받으면 pinned 그룹 안에서만 위치가 재정렬된다.
- unpin된 thread는 unpinned 그룹으로 내려가고, 그 안에서 최근 활동순 위치를 다시 계산한다.
- pinned badge 표시는 정렬과 별개가 아니라 같은 source of truth를 공유해야 한다.

## 완료 기준

- 사용자가 pin을 누르면 해당 thread는 즉시 최상단 pinned 그룹으로 이동한다.
- 새로고침 후에도 같은 순서를 유지한다.
- optimistic UI와 API 재조회 결과가 같은 순서를 보인다.
