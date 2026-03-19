# Async Stream DB Cleanup Refactor Plan

목표: SSE 스트림이 중간에 취소되더라도 `AsyncSession`/`asyncpg` 커넥션이 GC 경로로 정리되지 않게 하고, trace/log flush가 가능한 범위에서 안정적으로 완료되도록 리팩토링한다.

## Context

- 현재 `/api/chat`, `/api/chat/resume`는 FastAPI dependency로 주입된 `AsyncSession`을 스트리밍 제너레이터 안에서 장시간 사용한다.
- 클라이언트 disconnect 시 `CancelledError`와 SSE 종료 타이밍이 겹치면서 SQLAlchemy pooled connection이 정상 반환되지 않고, docker 로그에 다음 경고가 남는다.
  - `The garbage collector is trying to clean up non-checked-in connection`
- 이 문제는 기능 오류보다는 리소스 수명 관리 문제에 가깝다.

## Refactor Goals

1. 스트리밍 실행과 DB 세션 수명을 분리한다.
2. disconnect/cancelled 상황에서도 trace flush를 가능한 범위에서 보장한다.
3. 로그/트레이스 저장은 스트림 본문과 독립된 짧은 세션으로 처리한다.
4. `/api/chat`와 `/api/chat/resume`의 cleanup 정책을 공통화한다.

## Task TODO

- [x] 계획 문서 작성 및 작업 범위 확정
- [x] `/api/chat`, `/api/chat/resume`에서 request-scoped `db` dependency 제거
- [x] user message / resume message 사전 저장을 fresh session helper로 분리
- [x] final assistant log 저장을 fresh session helper로 분리
- [x] trace flush를 fresh session helper + cancellation-safe cleanup으로 분리
- [x] chat/resume 공통 cleanup 유틸 추출
- [x] disconnect edge case 테스트 보강
- [x] targeted test 실행 및 docker 로그 재검증

## Implementation Notes

- `AsyncSessionLocal`을 스트리밍 라우트에서 직접 사용한다.
- 스트림 시작 전 필요한 DB 작업은 라우트 함수에서 짧게 열고 닫는다.
- 스트림 종료 후 trace/log 저장은 `asyncio.shield(...)`로 감싸 취소 전파를 줄인다.
- cleanup 실패는 사용자 응답을 망치지 않되, stderr에는 남긴다.

## Validation

- 자동 테스트
  - disconnect 시 trace persist 보장
  - fresh session close/exit 경로 확인
  - 기존 error handling / resume edge case 회귀 없음
- 수동 검증
  - `curl`로 스트림 시작 후 중간 종료
  - docker backend 로그에서 asyncpg GC warning 재현 여부 확인
