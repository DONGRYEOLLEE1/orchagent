작성일시: 2026-03-24 10:57 KST
최종 수정일시: 2026-03-24 10:57 KST

# AI Thread Title Summarization Contract

## 요약

- AI 스레드 제목 생성은 새 thread의 첫 user message 전송 시에만 실행한다.
- 제목 생성은 메인 `/api/chat` 스트림과 병렬로 수행한다.
- 제목 생성 실패가 메인 에이전트 응답을 막으면 안 된다.
- 수동 rename은 AI 제목보다 항상 우선한다.

## 모델 결정

- 사용자 요청에는 `gpt-5.4-nano`가 적혀 있었지만, 현재 OpenAI 공식 문서에서 확인되는 nano 계열 GPT-5 모델명은 `gpt-5-nano`다.
- 구현 기본값은 문서화된 현재 모델명인 `gpt-5-nano`를 사용한다.
- 이 결정은 런타임 모델 미지원 오류를 피하기 위한 보수적 선택이다.

## 실행 조건

- 새 draft thread에서 첫 질문을 전송할 때만 제목 생성 요청을 보낸다.
- 기존 thread 후속 질문에서는 제목 생성 요청을 보내지 않는다.
- 이미 `thread_profiles.title_override`가 있으면 AI 제목 생성 결과를 저장하지 않는다.

## 저장 정책

- AI 제목도 1차적으로 `thread_profiles.title_override`에 저장한다.
- 수동 rename이 같은 필드를 사용하므로, “수동 rename 우선” 정책은 다음으로 보장한다.
  - AI 응답 저장 직전 `title_override`가 이미 존재하면 저장을 건너뛴다.
  - AI가 먼저 저장되더라도, 이후 수동 rename이 덮어쓴다.

## 출력 정책

- 출력은 가능한 한국어 한 줄이어야 한다.
- 핵심 기술 키워드(RoPE, ALiBi, JWT 등)는 유지할 수 있다.
- 불필요한 조사, 요청형 어미, 인용 부호, 마크다운은 제거한다.
- 최대 길이는 24자로 제한한다.

## fallback 정책

- 프런트 optimistic title fallback은 기존 질문 truncate 값을 유지한다.
- AI 제목 생성 실패 또는 빈 출력이면 fallback title을 유지한다.

## 병렬화 정책

- 새 thread 첫 전송 시 프런트는 동시에 두 작업을 시작한다.
  - `/api/chat`
  - `/api/threads/{thread_id}/ai-title`
- 두 요청은 서로 기다리지 않는다.
- 제목 응답이 먼저 오면 목록 title만 먼저 바뀔 수 있다.
- 채팅 응답이 먼저 와도 제목 응답은 나중에 안전하게 반영할 수 있어야 한다.
