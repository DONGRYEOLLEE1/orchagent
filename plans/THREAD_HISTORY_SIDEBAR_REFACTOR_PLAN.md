# Thread History Sidebar Refactor Plan

이 문서는 왼쪽 패널의 `SESSION STATE` 아래에 과거 대화 스레드 목록을 노출하고, 특정 스레드를 클릭하면 해당 스레드의 대화 내용을 중앙 채팅 영역에 복원하는 기능을 위한 리팩토링 계획서입니다.
목표는 단순히 목록을 붙이는 수준이 아니라, 현재 코드베이스의 저장 구조, SSE 기반 실행 흐름, HITL resume, 좌우 패널 상태를 함께 고려해 안정적으로 확장 가능한 구조를 만드는 것입니다.

## 1. 목표

- [ ] 왼쪽 패널에 최근 대화 스레드 목록을 표시한다.
- [ ] 스레드 클릭 시 해당 스레드의 메시지 히스토리를 중앙 채팅 영역에 복원한다.
- [ ] 기존 `/api/chat` 및 `/api/chat/resume` 스트리밍 흐름과 충돌 없이 같은 `thread_id`를 이어서 사용할 수 있게 만든다.
- [ ] 현재 단일 파일 중심 프론트 상태를 thread-aware 구조로 재정리한다.
- [ ] 이후 검색, 삭제, 제목 변경, pinned threads 같은 기능을 붙일 수 있도록 API/상태 모델을 정돈한다.

## 2. 현재 코드베이스 진단

### 2.1 프론트엔드

- [x] `apps/frontend/src/app/page.tsx` 안에 좌측 패널, 채팅창, 입력창, 우측 Action Space, SSE 이벤트 처리, thread 상태가 모두 한 파일에 몰려 있다.
- [x] `handleSubmit()`는 매 요청마다 `thread_${Date.now()}`를 새로 생성하므로, 사용자가 같은 대화 안에서 여러 턴을 자연스럽게 이어갈 수 없다.
- [x] 좌측 패널은 현재 `AgentTimeline`과 `Session Status`만 있고, 스레드 목록을 담을 별도 컴포넌트/상태 계층이 없다.
- [x] 과거 스레드를 다시 열기 위한 fetch 로직, loading/error 상태, 선택 상태가 없다.
- [x] 프론트 타입은 `ChatMessage`, `StreamEvent` 중심이며 thread summary/detail 타입이 없다.

### 2.2 백엔드

- [x] `ChatSession` / `ChatMessageLog` 모델이 이미 존재하므로 `thread_id` 단위의 대화 저장 기반은 있다.
- [x] 현재 `/api/chat`과 `/api/chat/resume`는 user/assistant 메시지를 DB에 저장한다.
- [x] 그러나 thread 목록/상세 조회용 API는 없고, 읽기 엔드포인트는 `/api/thread/{thread_id}/trace` 하나뿐이다.
- [x] `LoggingService.log_message()`는 메시지는 저장하지만 `ChatSession.updated_at`을 명시적으로 touch 하지 않아 최근 활동순 정렬의 신뢰도가 낮다.
- [x] 이미지 첨부는 파일로 저장되고 JSONL에 경로만 남으며, `chat_messages`에는 첨부 메타데이터가 저장되지 않는다.

### 2.3 구조적 제약

- [x] 현재 DB 스키마 변경은 Alembic migration 체계 없이 `Base.metadata.create_all()`에 의존한다.
- [x] 따라서 기존 테이블에 컬럼을 추가하는 설계는 바로 적용하기 어렵고, 1차 구현은 기존 스키마를 최대한 활용하거나 코드 레벨 보정으로 해결하는 것이 안전하다.
- [x] 인증이 없어 `user_id="anonymous_user"` 기반이므로 thread 목록은 사실상 단일 사용자/로컬 개발 기준으로만 안전하다.

## 3. 권장 UX 범위

### 3.1 이번 리팩토링의 권장 범위

- [ ] 왼쪽 패널 구성: `Agent Timeline` -> `Session State` -> `Threads` 순서 유지
- [ ] `Threads` 섹션 상단에 `New Chat` 버튼 추가
- [ ] 각 thread row는 최소한 다음 정보를 표시
  - [ ] 제목: 첫 번째 user 메시지 앞부분을 잘라서 사용
  - [ ] preview: 가장 최근 메시지 일부
  - [ ] 최근 활동 시각
  - [ ] 선택 상태
- [ ] thread 클릭 시 중앙 채팅 영역의 `messages`를 교체해 과거 대화 복원
- [ ] 선택된 thread에서 새 메시지를 보내면 기존 `thread_id`로 이어서 전송
- [ ] 새 대화 시작 시에만 새 `thread_id`를 발급

### 3.2 이번 리팩토링에서 의도적으로 단순화할 부분

- [ ] v1에서는 과거 thread 선택 시 `Tool Activity`, `Internal Reasoning`, `Raw Events`는 비우거나 read-only placeholder로 처리 가능
- [ ] v1에서는 thread 전환 중 active stream이 있으면 전환을 막거나 비활성화하는 정책을 우선 적용
- [ ] v1에서는 과거 이미지 첨부 복원은 제외하고, 텍스트 메시지 복원에 집중

### 3.3 후속 확장 후보

- [ ] thread rename / delete / pin / search
- [ ] 과거 trace를 이용한 `AgentTimeline` 및 `Action Space` 재구성
- [ ] 사용자별 thread 분리
- [ ] 첨부 파일/이미지 메타데이터 영속화

## 4. 목표 아키텍처

### 4.1 백엔드 API 권장안

- [ ] `GET /api/threads`
  - 최근 thread 목록 반환
  - 응답 필드: `thread_id`, `title`, `preview`, `created_at`, `last_activity_at`, `message_count`, `latest_status`, `checkpoint_id`
- [ ] `GET /api/threads/{thread_id}`
  - 선택한 thread의 메시지 히스토리와 세션 요약 반환
  - 응답 필드: `thread`, `messages`
- [ ] 기존 `GET /api/thread/{thread_id}/trace`는 유지하되, 추후 `threads` 리소스 구조와 이름을 맞출지 검토

### 4.2 프론트 상태 권장안

- [ ] `thread list state`와 `active chat state`를 분리
- [ ] `selectedThreadId | null` 개념 도입
- [ ] `draft/new chat` 상태를 별도로 두어, 빈 화면과 실제 저장된 thread를 구분
- [ ] SSE 스트리밍 상태는 선택된 thread에 귀속되도록 정리
- [ ] thread 전환 시 `messages`, `history`, `checkpointId`, `streamError`, `isInterrupted` 초기화 규칙을 명시

## 5. 상세 작업 체크리스트

### Phase 0. 설계 고정

- [ ] thread 목록의 source of truth를 `chat_sessions` / `chat_messages` DB로 확정한다.
- [ ] `title`은 첫 user 메시지 기반 파생값으로 시작하고, 별도 컬럼 추가는 보류한다.
- [ ] `preview`는 최신 assistant 메시지 우선, 없으면 최신 user 메시지로 파생한다.
- [ ] `last_activity_at`은 메시지 기준으로 계산하고, 동시에 `ChatSession.updated_at`도 함께 갱신하도록 보정한다.
- [ ] v1 thread switching 정책을 확정한다.
  - 권장: `loading` 또는 `isInterrupted` 중에는 다른 thread 선택 비활성화

### Phase 1. 백엔드 도메인/조회 계층 정리

- [ ] `services/logging_service.py`에 session touch 로직 추가
  - 메시지 저장 시 `ChatSession.updated_at`을 현재 시각으로 갱신
- [ ] thread summary 조회용 쿼리 로직을 별도 서비스로 분리
  - 권장 파일: `apps/backend/services/thread_service.py`
- [ ] 목록 조회 시 N+1 없이 동작하도록 aggregate/subquery 기반으로 설계
- [ ] 첫 user 메시지, 최신 메시지, 메시지 수, 마지막 활동 시각을 효율적으로 뽑는 쿼리 작성
- [ ] interrupted/completed/errored 상태를 어떻게 계산할지 규칙 정의
  - 권장: 최신 `status` trace 또는 최신 checkpoint/summary trace 기준
- [ ] 이미지가 있는 과거 대화는 현재 텍스트만 복원된다는 제한을 API 설계에 반영

### Phase 2. 백엔드 API 추가

- [ ] thread 목록 응답용 schema 추가
  - 권장 파일: `apps/backend/schemas/thread.py`
- [ ] thread 상세 응답용 schema 추가
- [ ] `GET /api/threads` 엔드포인트 구현
  - pagination 또는 `limit` 지원
  - 최신순 정렬
- [ ] `GET /api/threads/{thread_id}` 엔드포인트 구현
  - 메시지 생성 시각 오름차순 정렬
  - 존재하지 않는 thread는 404
- [ ] 필요 시 `GET /api/threads/{thread_id}/summary` 없이 detail 응답에 세션 요약 포함
- [ ] `main.py`에 새 router 연결 또는 기존 `chat.py`에 임시 추가
- [ ] 응답 timestamp 포맷을 일관된 ISO 문자열로 고정

### Phase 3. 백엔드 테스트

- [ ] `LoggingService.log_message()`가 `updated_at`을 실제로 갱신하는 테스트 추가
- [ ] thread 목록 API 테스트 추가
  - [ ] 빈 목록
  - [ ] 최신순 정렬
  - [ ] preview/title 파생
  - [ ] message_count 계산
- [ ] thread 상세 API 테스트 추가
  - [ ] 메시지 순서 보장
  - [ ] 잘못된 `thread_id` 404
  - [ ] user만 있고 assistant가 아직 없는 thread
  - [ ] resume 이후 메시지가 이어진 thread
- [ ] trace/status 기반 최신 상태 계산 로직 테스트 추가
- [ ] 기존 `/api/chat`, `/api/chat/resume` 테스트가 회귀하지 않는지 확인

### Phase 4. 프론트 타입/상태 계층 분리

- [ ] `apps/frontend/src/types/agent.ts` 또는 별도 `thread.ts`에 다음 타입 추가
  - [ ] `ThreadSummary`
  - [ ] `ThreadDetail`
  - [ ] `ThreadMessage`
  - [ ] `ThreadLoadState`
- [ ] API 호출 코드를 page 파일에서 분리
  - 권장 파일: `apps/frontend/src/lib/api.ts`
- [ ] thread 목록/상세 fetch 로직을 재사용 가능한 함수로 분리
- [ ] `page.tsx`의 monolithic 상태를 다음 계층으로 정리
  - [ ] thread collection state
  - [ ] active thread state
  - [ ] stream session state
  - [ ] action space state

### Phase 5. 프론트 UI 리팩토링

- [ ] 좌측 패널 width 재설계
  - 현재 `lg:w-64`는 thread preview가 좁으므로 `lg:w-80` 또는 유사 폭으로 조정 검토
- [ ] `ThreadListSidebar` 컴포넌트 분리
- [ ] `ThreadListItem` 컴포넌트 분리
- [ ] `SessionStatusCard` 컴포넌트 분리
- [ ] `AgentTimeline`을 left sidebar 안에서 독립 컴포넌트로 유지
- [ ] `New Chat` 버튼 추가
- [ ] 빈 thread 목록 상태(empty state) 디자인 추가
- [ ] 현재 선택된 thread 강조 스타일 추가
- [ ] 왼쪽 패널 스크롤 영역을 `timeline/status`와 `threads`로 분리해 overflow 충돌 방지
- [ ] 모바일/좁은 화면에서는 thread drawer 또는 collapsible section 처리 방안 반영

### Phase 6. 프론트 상호작용/복원 로직

- [ ] 앱 초기 진입 시 최근 thread 목록 fetch
- [ ] thread 클릭 시 detail fetch 후 중앙 채팅 영역 hydrate
- [ ] thread 변경 시 중앙 헤더의 thread 표시도 동기화
- [ ] 새 대화 시작 시 빈 draft 상태로 전환
- [ ] 메시지 전송 시 규칙 변경
  - [ ] draft 상태면 새 `thread_id` 생성
  - [ ] 기존 thread 선택 상태면 해당 `thread_id` 재사용
- [ ] 첫 메시지 전송 시 thread row를 optimistic insert
- [ ] assistant 응답 완료 시 preview / last_activity_at 갱신
- [ ] resume도 동일 thread summary를 갱신
- [ ] thread 선택 시 `history`, `checkpointId`, `isInterrupted`, `streamError`, `toolExecutions`, `reasoning`, `rawTraces`를 어떻게 처리할지 명시
  - 권장 v1: 메시지만 복원, action-space 상태는 clear
- [ ] thread 전환 중 active stream 차단 또는 경고 UX 적용

### Phase 7. 과거 thread의 상태 패널 복원 범위 결정

- [ ] `Session State` 카드에 어떤 정보를 historical thread에서도 보여줄지 확정
  - [ ] latest status
  - [ ] latest checkpoint id
  - [ ] last activity time
- [ ] `AgentTimeline`을 historical thread에서도 보여줄지 결정
  - 권장 v1: 현재 세션용 live timeline만 유지
  - 후속: trace API로 historical timeline 복원
- [ ] `Action Space`의 reasoning/tool/raw events를 historical thread에 대해 hydrate할지 결정
  - 권장 v1: hydrate 미지원

### Phase 8. 프론트 테스트 체계 보강

- [ ] 현재 프론트 테스트는 `node:test` 기반의 순수 helper 테스트만 있으므로, UI 상호작용 검증 도구를 보강한다.
- [ ] 선택지 결정
  - [ ] `Vitest + @testing-library/react + jsdom` 도입
  - [ ] 또는 최소한 thread state reducer/helper를 분리해 순수 로직 테스트부터 확보
- [ ] 필수 테스트 시나리오
  - [ ] thread 목록 렌더링
  - [ ] thread 클릭 시 detail hydrate
  - [ ] new chat 전환
  - [ ] 같은 thread에서 연속 메시지 전송 시 `thread_id` 유지
  - [ ] active stream 중 thread switching 비활성화
  - [ ] empty/error loading state

### Phase 9. 통합 검증

- [ ] 수동 시나리오 1: 새 대화 생성 -> 2턴 이상 대화 -> 새로고침 -> 동일 thread 재선택 시 메시지 복원
- [ ] 수동 시나리오 2: interrupted thread 생성 -> 새로고침 -> thread 재선택 -> resume 가능 여부 확인
- [ ] 수동 시나리오 3: 최근순 정렬이 실제 활동순과 일치하는지 확인
- [ ] 수동 시나리오 4: 여러 thread를 전환해도 현재 SSE/scroll/UI 상태가 꼬이지 않는지 확인
- [ ] 수동 시나리오 5: 이미지 포함 thread가 텍스트 중심으로라도 안전하게 복원되는지 확인

## 6. 권장 구현 순서

1. 백엔드 조회 API와 `updated_at` 보정부터 먼저 완료
2. 프론트에서 thread list / detail hydrate / new chat draft 도입
3. 기존 submit/resume 로직을 selected thread 기반으로 재연결
4. 좌측 패널 UI 정리 및 mobile fallback 추가
5. historical thread에서 session state/timeline을 어디까지 복원할지 2차 확장

## 7. 리스크 및 주의사항

- [ ] 현재 인증이 없으므로 thread 목록은 다중 사용자 환경에서 안전하지 않다.
- [ ] 스키마 migration 체계가 없으므로, 초기 단계에서 컬럼 추가 전제를 깔면 작업이 불안정해진다.
- [ ] active streaming 중 thread를 바꾸는 UX는 구현 난도가 높다. v1에서 차단하는 편이 안정적이다.
- [ ] historical thread에 tool/reasoning을 억지로 복원하려 하면 trace API 응답량과 프론트 상태 복잡도가 급격히 커진다.
- [ ] 이미지 복원까지 한 번에 해결하려면 message attachment 모델이 필요할 가능성이 높다.

## 8. 완료 기준

- [ ] 왼쪽 패널 `SESSION STATE` 아래에 thread 목록이 렌더링된다.
- [ ] 과거 thread 클릭 시 중앙 채팅창에 해당 메시지 히스토리가 표시된다.
- [ ] 동일 thread에서 추가 메시지를 보내면 thread가 이어지고 새 thread가 남발되지 않는다.
- [ ] 최근 활동한 thread가 목록 상단으로 정렬된다.
- [ ] 기존 chat/resume/trace 흐름이 회귀하지 않는다.
