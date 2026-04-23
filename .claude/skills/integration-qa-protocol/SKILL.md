---
name: integration-qa-protocol
description: "OrchAgent의 통합 정합성(경계면) 교차 검증 프로토콜. 백엔드 API 응답 shape ↔ 프론트 훅/타입, SSE 이벤트 ↔ 파서, LangGraph state ↔ SSE emit, supervisor 허용 전이 ↔ 실제 Command.goto, `src/app/` 페이지 경로 ↔ href를 양쪽을 동시에 읽고 비교하는 방법. 새 엔드포인트/컴포넌트/state 필드 완성 직후 점진적으로 적용한다. 경계면 버그 디버깅 시에도 반드시 이 스킬을 사용한다."
---

# Integration QA Protocol — 양쪽 동시 읽기 교차 검증

OrchAgent 경계면 버그의 대다수는 "각 모듈이 정상이지만 연결이 어긋남"에서 발생. 이 스킬은 양쪽을 동시에 열고 비교하는 구체적 절차를 정의한다.

## 핵심 원칙

1. **존재 확인 금지, 교차 비교 의무** — "API가 있나?"가 아니라 "API 응답 shape이 훅 타입과 일치하나?"
2. **양쪽 파일을 동시에 open** — 한 쪽만 보고는 경계면 버그를 찾지 못한다
3. **점진적 적용** — 전체 완성 후 1회 몰아치기 금지. 모듈 완성 직후 해당 경계면만 빠르게 검사
4. **TypeScript 제네릭의 거짓 안심 경계** — `fetchJson<T>()` 캐스팅은 런타임 불일치를 숨긴다. 백엔드 응답 코드를 실제로 읽어야 한다

## 5대 경계면 검증

### 1. API 응답 shape ↔ 프론트 훅/타입

**절차**:
1. Grep으로 대상 API route 찾기: `rg "JSONResponse|PlainTextResponse" apps/backend/api/`
2. 해당 엔드포인트의 response_model(Pydantic) 또는 실제 반환 객체 확인
3. 프론트에서 같은 path를 호출하는 훅/함수 찾기: `rg "{path}" apps/frontend/src`
4. `fetchJson<T>`의 T 타입과 실제 응답 shape을 **필드별로** 비교
5. 래핑 여부 확인 — API가 `{items: [...]}`이면 훅이 `.items`로 unwrap하는지
6. snake_case ↔ camelCase 변환 지점 확인 (한 곳에서만)

**자주 놓치는 패턴**:
- 페이지네이션 API: `{items, total, page}` vs 프론트가 바로 배열 기대
- 즉시 응답(202): 비동기 결과 shape과 즉시 응답 shape 혼동
- optional 필드의 null vs undefined 처리 불일치

### 2. SSE 이벤트 ↔ 프론트 파서

**절차**:
1. 백엔드 SSE emit 지점 확인: `rg "event:.*data:" apps/backend` 또는 SSE 래퍼 함수
2. 각 event type별로 data 객체 shape 추출
3. 프론트 파서(`src/lib/chat-stream.*`, `workspace-state.ts`) 열기
4. dispatch 분기(switch/match)에서 **모든** 백엔드 타입이 처리되는지 확인
5. 미지 타입 처리(crash vs skip) 검증
6. `sse-contract` 스킬의 shape과 양쪽 실제 코드 대조

**자주 놓치는 패턴**:
- 백엔드에서 새 type 추가 후 프론트 미반영 (UI에 안 보임)
- 필드명 오탈자(`reason` vs `reasoning`)
- `is_final=true` 텍스트가 두 번 emit (OWNERSHIP 위반)

### 3. LangGraph state ↔ SSE emit 필드

**절차**:
1. `packages/agent-core/src/agent_core/state.py`에서 state 필드 목록 추출
2. 백엔드 SSE 스트림 핸들러에서 emit하는 필드가 state의 어떤 필드와 매핑되는지 추적
3. state에 있지만 emit되지 않는 필드, 반대로 state에 없는데 emit하는 필드 식별
4. 각 필드의 reducer/optional 여부가 SSE payload에 반영되는지

### 4. Supervisor 허용 전이 ↔ 실제 `Command.goto`

**절차**:
1. `agent_core/supervisor.py`에서 허용 전이(허용되는 다음 노드 집합) 식별
2. Grep: `rg "Command\(goto=" apps/backend packages/agent-core`
3. 각 goto 대상이 허용 전이에 포함되는지 확인
4. 맵에 정의되었지만 코드에서 도달 못하는 "죽은 전이" 식별
5. `retry_count` 상한 도달 시 강제 종료 경로 검증

### 5. 파일 경로 ↔ `href` / `router.push`

**절차**:
1. `apps/frontend/src/app/` 하위 `page.tsx` 파일들의 URL 경로 추출
   - `(workspace)` 같은 route group은 URL에서 제거
   - `[param]`은 동적 세그먼트
2. Grep: `rg "href=|router\.push\(|redirect\(" apps/frontend/src`
3. 각 경로가 실제 페이지와 매칭되는지 확인
4. `/dashboard/*` 같은 접두사 누락 주의

## 실행 도구

- **테스트**: `uv run pytest apps/backend/tests/<관련>.py -v`, `cd apps/frontend && npm run test -- <관련>`, `node --test <파일>`, `npm run build`
- **Grep/Glob** 광범위 조사
- 실패 시 파일:라인과 정확한 diff 제안

## 리포트 템플릿

`_workspace/qa_report_{topic}.md`에 저장:

```markdown
# QA Report — {topic}
생성: {ts}

## 검증 범위
- {경계면1}, {경계면2}, ...

## 통과
- [x] API /api/X 응답 shape ↔ useXHook 타입 일치 (확인 파일: api/x.py:L, lib/api.ts:L)

## 실패 / 수정 필요
- [ ] SSE `checkpoint` 이벤트에 `can_resume` 필드 있으나 프론트 파서 미처리 (chat-stream.ts:L45)
  - 수정 요청: frontend-engineer에게
  - 수정안: switch case 추가 + workspace-state 리듀서에 resumable 플래그 반영

## 테스트 실행 결과
- pytest tests/test_X.py: PASS (n=12)
- npm run test src/lib/chat-stream.test.mjs: PASS

## 리스크
- {remaining risk}
```

## 팀 통신 (QA-verifier 전용)

- 경계면 이슈 발견 시 **양쪽 에이전트 모두에게** SendMessage (producer + consumer)
- 메시지에는 반드시: 파일:라인, 불일치 상세, 제안 수정안
- QA가 직접 수정하지 않고 요청 — 원 작성자의 맥락이 정확함

## 체크리스트 (새 변경 직후)

- [ ] 변경된 경계면 5종 중 몇 개에 영향?
- [ ] 양쪽 파일을 실제로 열어 대조했나?
- [ ] 관련 기존 테스트가 여전히 의미 있나?
- [ ] 새 테스트가 경계면을 보호하나? (단위 테스트만으론 부족)
- [ ] contract 문서(`sse-contract`, `docs/*_CONTRACT.md`) 갱신 필요?

## 관련 참조

- `docs/FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT.md` — 치명적 계약
- `docs/FINAL_RESPONSE_STREAM_DUPLICATION_INCIDENT.md` — 경계면 사고 회고
- `plans/BACKEND_QA_TEST_PLAN.md` — QA 전략
- `docs/AI_THREAD_TITLE_SUMMARIZATION_CONTRACT.md`, `docs/PINNED_THREAD_TOP_ORDER_CONTRACT.md` — 추가 계약
