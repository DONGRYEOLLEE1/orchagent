작성일시: 2026-03-24 10:01 KST
최종 수정일시: 2026-03-24 10:01 KST

# Final Response Stream Duplication Incident

## 요약

- 증상: 웹검색 기반 질의에서 assistant 최종 답변이 UI에 3회 반복 노출되고, 같은 중복 문자열이 `chat_messages.content`에도 저장된다.
- 영향 범위: `/api/chat`, `/api/chat/resume`, thread preview, `text_summary` trace, DB persistence.
- 심각도: 높음. 사용자 응답 품질과 영속 데이터 정합성을 동시에 깨뜨린다.

## 재현 질의

- `웹검색을 통해 RoPE 알고리즘을 검색하여 500자 내외로 설명해줘.`

## 확인된 실제 데이터

### 1. DB persisted assistant row

- thread id: `thread_1774255093186`
- row id: `d28b8a21-1c06-49be-b5bb-4dd89a4bbbbd`
- role: `assistant`
- persisted `content` 길이: `1087`
- persisted `content`는 동일 답변 블록이 3회 연속 누적된 형태였다.

### 2. Final checkpoint state

- 같은 turn의 final checkpoint state 안 마지막 `assistant` 메시지는 1개만 존재했다.
- final checkpoint assistant content 길이는 `363`이었다.
- 결론: 최종 state 생성 자체는 1회 정상 완료됐고, 중복은 스트림 누적 경로에서 발생했다.

### 3. 실재현 stream ownership 관찰

- 동일 계열 질의를 새 thread에서 재실행했을 때 최종 텍스트가 서로 다른 3개 run에서 모두 수집됐다.
- 관찰된 owner 후보:
  - `head_supervisor` speculative final text 1회
  - `head_supervisor` speculative final text 1회 더
  - `finalizer` final text 1회
- 결론: “같은 답변을 3번 append한 것”이 아니라 “서로 다른 3개의 최종 답변 후보 run을 모두 최종 응답으로 취급한 것”이다.

## 실패 조건

- 한 turn의 UI assistant bubble에 동일 최종 답변 블록이 2회 이상 반복되면 실패다.
- `chat_messages.content`가 canonical final answer와 다르면 실패다.
- 한 turn 안에서 final answer owner run이 2개 이상이면 실패다.

## 진단 포인트

### 1. `head_supervisor` speculative stream

- `head_supervisor`가 구조화 출력에서 `content`를 먼저 생성하는지 확인한다.
- 이 stream이 실제 route 확정 전에 사용자 채널로 흘러가는지 확인한다.

### 2. `head_supervisor` override 후 reroute

- task plan progression으로 `writing_team`으로 override되는지 확인한다.
- 이후 다시 `finalizer`로 reroute되는지 확인한다.
- 위 reroute가 발생한 뒤에도 앞선 speculative text가 폐기되지 않는지 확인한다.

### 3. `finalizer` 최종 stream

- `finalizer`가 canonical final answer를 1회 생성하는지 확인한다.
- 앞선 `head_supervisor` stream이 이미 누적된 상태에서 `finalizer` 결과가 추가로 붙는지 확인한다.

## 관찰 결론

- 이 incident의 본질은 프런트 렌더링 이슈가 아니다.
- 이 incident의 본질은 stream owner 계약 부재와 speculative text 누적 허용이다.
- 따라서 수정 방향은 UI 패치가 아니라 “단일 final answer owner 계약”과 “run-aware stream collector”로 가야 한다.
