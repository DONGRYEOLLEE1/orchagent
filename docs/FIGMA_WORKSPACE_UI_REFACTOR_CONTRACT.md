작성일시: 2026-03-24 13:57 KST

# Figma Workspace UI Refactor Contract

## 요약

- 구현 대상 Figma 범위는 메인 워크스페이스 `25:2`와 로그인 화면 `46:3`으로 고정한다.
- 하단 푸터/빈 레이아웃 영역 `46:2`는 구현 대상에서 제외한다.
- 상단 메뉴는 `Chat`만 실제 제품 기능으로 구현한다.
- `Dashboard`, `Agents`, `Logs`, `Settings`는 이번 리팩토링 범위 밖이며, 향후 최종 제품에 모두 포함된다고 가정하지 않는다.

## 워크스페이스 역할 정의

### 좌측 패널

- 스레드 아카이브와 `New Chat` 진입을 담당한다.
- 기존 AI 스레드 제목 생성 기능을 유지한다.
- 스레드명 좌측 아이콘은 추가하지 않는다.

### 중앙 패널

- 사용자/assistant 메시지와 입력창의 주 작업 공간이다.
- assistant 응답 상단에는 compact `Tool Calling Statuses` 1줄 strip을 둔다.
- 이 strip은 최근 tool activity를 간략히 보여주되, 디버그 패널처럼 장황하게 확장하지 않는다.

### 우측 패널

- 실시간 telemetry 전용 패널로 고정한다.
- 포함 항목:
  - `Agent Timeline`
  - `Inner Monologue`
  - `Suggested Queries`
- 제외 항목:
  - `ProfilePanel`
  - `AdminStatusPanel`
- 위 두 계정 관리 패널은 상단 프로필 액션으로 이동한다.

## Reasoning Summary 계약

- `Inner Monologue`는 AI의 전체 chain-of-thought가 아니라 `reasoning summary`만 표출한다.
- live turn에서는 기존 SSE `reasoning` 이벤트를 실시간 누적해 패널에 반영한다.
- historical thread에서는 저장된 최신 `reasoning_summary` trace event를 hydrate한다.
- historical telemetry가 없을 때는 misleading한 빈 reasoning 재생 대신 명시적 fallback copy를 사용한다.

## Tool Calling Statuses 계약

- source는 기존 SSE `tool_start`, `tool_end`, `tool_error` 이벤트를 재사용한다.
- 중앙 assistant response 상단에 최근 1~3개 상태만 compact하게 노출한다.
- 사용자에게 “현재 어떤 도구 단계가 진행 중인지”를 짧게 보여주는 것이 목적이다.
- 세부 입출력은 우측 telemetry 또는 개발자용 raw trace panel에서 다룬다.

## Suggested Queries 계약

- 추천 질문은 현재 활성 스레드의 최신 `user -> assistant` 문답 1쌍만 참조한다.
- 생성 시점은 최종 답변이 모두 표출된 뒤다.
- 즉, main answer stream 완료 전에는 추천 질문 생성이 시작되면 안 된다.
- 추천 질문 생성은 메인 답변의 TTFT나 스트리밍 품질을 절대 블로킹하지 않는다.
- 출력은 한국어 우선의 짧은 후속 질문 3~4개로 제한한다.
- 추천 질문은 클릭 시 입력창에 주입하거나 바로 후속 질문으로 사용할 수 있어야 한다.

## Suggested Queries 저장 계약

- 1차 구현에서는 새 테이블을 추가하지 않는다.
- 추천 질문 결과는 `trace_events`에 `suggested_queries_summary` 이벤트로 저장한다.
- historical thread rehydrate 시 이 이벤트를 읽어 우측 패널에 복원한다.

## 구현 불변 조건

- 기존 최종 답변 중복 방지 로직을 깨뜨리지 않는다.
- 기존 HITL interrupt/resume 경로를 유지한다.
- 기존 AI thread title, pin, rename, delete 동작을 유지한다.
- 없는 화면을 억지로 구현하기 위해 가짜 라우트나 깨진 상단 메뉴를 만들지 않는다.
