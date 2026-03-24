작성일시: 2026-03-24 10:57 KST
최종 수정일시: 2026-03-24 11:18 KST

# AI Thread Title Summarization Plan

목표: 사용자가 새 스레드에서 첫 질문을 전송하는 즉시 `gpt-5-nano`를 사용해 짧고 직관적인 한국어 스레드 제목을 생성하고, 이 작업이 메인 에이전트 응답 생성과 병렬로 수행되도록 만든다.

## 1. 문제 정의

- 현재 새 스레드의 제목은 프런트에서 첫 사용자 질문을 잘라서 그대로 사용한다.
- 이 방식은 질문이 길거나 복합적인 경우 왼쪽 스레드 목록에서 핵심 목적이 한눈에 들어오지 않는다.
- 예:
  - 사용자 질문: `웹검색을 통해 RoPE 논문을 탐색하고 메인 연구자가 원하는 바는 무엇인지 설명해주세요.`
  - 현재 제목: 질문 원문 일부
  - 목표 제목: `RoPE 논문 탐색`

## 2. 현재 구조 진단

### 2.1 프런트엔드

- `apps/frontend/src/lib/workspace-state.ts`
  - `createOptimisticThreadSummary()`가 현재 `content`를 80자 truncate 해서 `title`로 사용한다.
- `apps/frontend/src/app/page.tsx`
  - 새 draft thread 전송 시 optimistic thread summary를 즉시 목록에 넣는다.
  - 현재는 `/api/chat` 스트림 요청만 보낸다.

### 2.2 백엔드

- `apps/backend/services/thread_service.py`
  - 서버 summary도 기본적으로 첫 user message를 잘라 `title`로 파생한다.
- `apps/backend/models/thread_profile.py`
  - `title_override`가 이미 있어 수동 rename을 저장하는 데 사용된다.
- `apps/backend/api/routes/threads.py`
  - thread patch API가 있어 제목 덮어쓰기가 이미 가능하다.

### 2.3 프롬프트/LLM 제약

- 실제 런타임 LLM 초기화는 반드시 `langchain.chat_models.init_chat_model`을 사용해야 한다.
- 새 프롬프트는 반드시 `packages/prompt-kit/src/prompt_kit/prompts.py`에 정의해야 한다.
- 애플리케이션 코드에 제목 요약용 시스템 프롬프트를 하드코딩하면 안 된다.

## 3. 설계 목표

- 새 스레드의 첫 질문에 대해서만 AI 제목 요약을 수행한다.
- 제목 요약은 메인 `/api/chat` 스트림과 병렬로 실행한다.
- 제목 생성 실패 시에도 대화 응답은 영향을 받지 않아야 한다.
- 제목은 짧고 목록 친화적이어야 하며, 가능하면 한국어로 출력되어야 한다.
- 기술 키워드나 고유명사(RoPE, ALiBi, JWT 등)는 필요 시 그대로 유지해야 한다.
- 사용자가 수동 rename한 제목은 AI 제목보다 항상 우선한다.

## 4. 핵심 정책

### 4.1 언제 제목을 생성할 것인가

- 새 draft thread에서 첫 user message를 전송할 때만 실행한다.
- 기존 thread에 후속 질문을 보낼 때는 실행하지 않는다.
- 이미 `thread_profiles.title_override`가 존재하면 생성하지 않는다.

### 4.2 어디에 저장할 것인가

- 1차 구현에서는 새 컬럼을 추가하지 않고 기존 `thread_profiles.title_override`를 재사용한다.
- 이유:
  - 이미 수동 rename 저장 경로가 존재한다.
  - 현재 코드베이스는 스키마 변경 비용이 상대적으로 크다.
  - “AI 제목도 override”로 취급하고, 수동 rename이 나중에 덮어쓰는 정책으로도 충분히 동작한다.

### 4.3 manual rename 충돌 정책

- 수동 rename이 항상 최우선이다.
- AI 제목 저장 시점에 `title_override`가 이미 채워져 있으면 AI 제목 쓰기를 건너뛴다.
- 즉:
  - AI 제목이 먼저 저장되면, 이후 수동 rename이 이를 덮어쓴다.
  - 수동 rename이 먼저 저장되면, 이후 늦게 도착한 AI 제목은 무시한다.

### 4.4 출력 형식 정책

- 기본 출력 언어는 한국어로 유도한다.
- 단, RoPE, ALiBi, JWT, OAuth 같은 핵심 식별자는 그대로 유지할 수 있게 한다.
- 출력 제한:
  - 한 줄
  - 불필요한 조사/군더더기 제거
  - 따옴표, 마침표, 콜론, 마크다운 금지
  - 권장 길이: 6~18자 내외
  - 최대 길이: 24자

## 5. 권장 아키텍처

### 권장안: 프런트 병렬 요청 + 백엔드 제목 요약 엔드포인트

- 새 thread 첫 전송 시 프런트는 다음 두 작업을 동시에 시작한다.
- 작업 1: 기존 `/api/chat` 스트림 요청
- 작업 2: 새 AI 제목 생성 요청

### 이유

- 사용자가 요구한 `질문 -> 스레드명 요약 -> 에이전트 답변 생성`의 순차 흐름을 피할 수 있다.
- 제목 생성 실패가 메인 답변 스트림을 블로킹하지 않는다.
- title generation concern을 메인 chat stream 로직과 분리할 수 있다.

### 권장 엔드포인트 형태

- `POST /api/threads/{thread_id}/ai-title`
- request body:
  - `message`: 첫 사용자 질문
- response:
  - 업데이트된 `ThreadSummary` 또는 최소한 `{ thread_id, title }`

### 권장 프런트 호출 방식

- `handleSubmit()`에서 새 thread인 경우:
  - optimistic title은 기존처럼 질문 truncate를 먼저 사용한다.
  - `sendChatStream(...)` 시작
  - 동시에 `generateAiThreadTitle(...)` 호출
  - 제목 응답이 먼저 오면 thread list title만 patch
  - 채팅 응답이 먼저 와도 title 응답은 나중에 안전하게 patch

## 6. 프롬프트 설계 원칙

### 새 프롬프트 정의 위치

- `packages/prompt-kit/src/prompt_kit/prompts.py`

### 새 프롬프트 역할

- 사용자의 첫 질문을 thread list 친화적인 짧은 제목으로 요약한다.
- 질문의 “행동 목적”이 가장 도드라지게 드러나야 한다.
- 형식적 친절 표현, 질문 문장, 세부 조건 나열을 제거한다.

### 프롬프트 핵심 제약

- 출력은 반드시 한 줄
- 가능하면 한국어
- 핵심 명사 + 작업 목적 중심
- 기술 키워드는 보존 가능
- 24자 이내
- 의미가 흐려지는 과도한 일반화 금지

### 예시 few-shot에 포함할 항목

- `웹검색을 통해 RoPE 논문을 탐색하고 메인 연구자가 원하는 바는 무엇인지 설명해주세요.`
  - `RoPE 논문 탐색`
- `JWT와 세션 쿠키의 차이를 비교하고 우리 서비스에 더 적합한 방식을 추천해줘`
  - `JWT vs 세션 쿠키`
- `회원가입 실패 로그를 보고 왜 validation error가 나는지 찾아줘`
  - `회원가입 에러 분석`

## 7. 모델 선택

- 제목 요약 전용 모델은 `gpt-5-nano`로 고정한다.
- reasoning summary 같은 부가 옵션은 기본적으로 불필요하다.
- structured output으로 다음 스키마를 권장한다.
  - `title: str`

## 8. 상세 작업 체크리스트

### Phase 0. 제목 생성 계약 고정

- [x] AI 제목 생성은 “새 thread의 첫 user message”에만 실행된다는 계약을 문서화한다.
- [x] 수동 rename 우선 정책을 고정한다.
- [x] 제목 저장은 1차적으로 `thread_profiles.title_override`를 재사용한다는 결정을 고정한다.
- [x] 제목 생성 실패 시 fallback은 기존 질문 truncate title 유지로 고정한다.

### Phase 1. 프롬프트와 title service 설계

- [x] `packages/prompt-kit`에 제목 요약용 prompt template를 추가한다.
- [x] 제목 요약용 Pydantic schema를 정의한다.
- [x] `gpt-5-nano`를 `init_chat_model`로 초기화하는 전용 service를 설계한다.
- [x] service는 입력 질문을 받아 정규화된 title string을 반환하도록 만든다.
- [x] 출력 정규화 로직을 별도 함수로 분리한다.
- [x] 공백 정리
- [x] 한 줄 강제
- [x] 최대 길이 제한
- [x] 빈 결과 시 fallback 처리

### Phase 2. 백엔드 API 추가

- [x] `POST /api/threads/{thread_id}/ai-title` 엔드포인트를 추가한다.
- [x] 요청 시 thread ownership을 검증한다.
- [x] 이미 `title_override`가 있으면 AI 제목 생성을 건너뛰거나 no-op 응답을 반환한다.
- [x] thread의 첫 user message인지 확인하는 정책을 구현한다.
- [x] 새 질문 본문을 service에 전달해 title을 생성한다.
- [x] 결과는 `ThreadProfileService`를 통해 저장한다.
- [x] 응답은 프런트가 즉시 title을 patch할 수 있는 형태로 반환한다.

### Phase 3. 프런트 병렬화 구현

- [x] `apps/frontend/src/lib/api.ts`에 AI 제목 생성 API 함수를 추가한다.
- [x] `handleSubmit()`에서 새 draft thread 여부를 판별한다.
- [x] 새 thread일 때 `sendChatStream(...)`과 `generateAiThreadTitle(...)`를 병렬 시작한다.
- [x] 제목 요청은 chat stream completion을 기다리지 않도록 만든다.
- [x] 제목 응답 성공 시 해당 thread summary의 `title`을 patch한다.
- [x] active thread가 같은 thread일 경우 중앙 헤더의 title도 함께 갱신한다.
- [x] 제목 요청 실패 시 사용자 대화는 계속 진행되고 fallback title을 유지한다.

### Phase 4. 충돌/경계 케이스 보강

- [x] 사용자가 AI 제목 생성 완료 전에 수동 rename한 경우 AI 제목 응답을 무시하도록 한다.
- [x] 기존 thread 후속 질문에서는 AI 제목 생성을 호출하지 않도록 한다.
- [x] 비어 있거나 너무 짧은 질문은 fallback title을 유지하도록 한다.
- [x] 한국어가 아닌 질문도 목록 친화적인 짧은 title이 나오도록 규칙을 정의한다.
- [x] 매우 긴 질문에서도 title이 잘리는 대신 의도가 보존되는지 확인한다.

### Phase 5. 테스트

- [x] backend service 단위 테스트를 추가한다.
- [x] 제목 정규화 테스트
- [x] 최대 길이 제한 테스트
- [x] 빈 출력 fallback 테스트
- [x] backend API 테스트를 추가한다.
- [x] 첫 질문에서만 생성되는지
- [x] 기존 `title_override` 존재 시 skip 되는지
- [x] 수동 rename 선점 시 overwrite 되지 않는지
- [x] frontend 테스트를 추가한다.
- [x] 새 thread 전송 시 제목 생성 API와 chat stream이 병렬 시작되는지
- [x] 제목 응답이 나중에 와도 목록 title이 patch 되는지
- [x] 제목 생성 실패 시 질문 truncate title이 유지되는지
- [x] 기존 thread 후속 질문 시 제목 생성 요청이 발생하지 않는지

### Phase 6. 수동 검증

- [x] 새 thread에서 긴 질문을 보내고 목록 title이 짧은 AI 제목으로 바뀌는지 확인한다.
- [x] chat 응답이 길게 걸려도 title이 먼저 반영될 수 있는지 확인한다.
- [x] manual rename 후 다시 첫 질문 title이 덮어써지지 않는지 확인한다.
- [x] 브라우저 새로고침 후에도 AI 제목이 유지되는지 확인한다.

### Phase 7. Playwright MCP 최종 검증

- [x] 실제 브라우저에서 새 thread를 시작한다.
- [x] `웹검색을 통해 RoPE 논문을 탐색하고 메인 연구자가 원하는 바는 무엇인지 설명해주세요.` 를 입력한다.
- [x] 채팅 응답 완료를 기다리지 않고도 thread title이 짧은 AI 제목으로 바뀌는지 관찰한다.
- [x] title이 질문 원문 truncate가 아니라 목적 중심 요약인지 확인한다.
- [x] 유사 질의 1~2개를 더 실행해 한국어 title 품질과 길이 제한을 확인한다.
- [x] DB에서 해당 thread의 `thread_profiles.title_override`가 기대값으로 저장됐는지 확인한다.

## 9. 검증 체크리스트

### 자동 검증 체크리스트

- [x] backend 단위 테스트 통과
- [x] backend API 테스트 통과
- [x] frontend 병렬화 테스트 통과
- [x] 제목 생성 실패 fallback 테스트 통과

### 실브라우저 검증 체크리스트

- [x] 새 thread 첫 질문에서만 AI 제목이 생성된다.
- [x] 제목 생성이 chat stream을 블로킹하지 않는다.
- [x] 제목이 한국어 중심의 짧은 한 줄 요약으로 들어간다.
- [x] manual rename 이후에는 AI 제목이 덮어쓰지 않는다.

## 10. 완료 조건

- 새 thread 첫 전송 시 `gpt-5-nano` 기반 AI 제목 생성이 병렬로 시작된다.
- 목록 title이 질문 원문 truncate보다 더 짧고 의도 중심적인 형태로 바뀐다.
- 메인 에이전트 답변 스트림은 title 생성 여부와 무관하게 정상 동작한다.
- 수동 rename과 충돌하지 않는다.
- 테스트와 Playwright 검증까지 완료되어 회귀 방어가 가능하다.
