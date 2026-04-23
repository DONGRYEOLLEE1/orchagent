---
name: plans-driven-workflow
description: "OrchAgent에서 `plans/*.md`를 근거로 코드 수정을 진행할 때 따라야 하는 워크플로우. 태스크 1개 → 검증 실행 → 체크박스 `- [x]` 반영 → 커밋 → push → 다음 태스크 루프, 커밋 컨벤션(`type(scope): summary`), plans 상단 요약 블록 규칙, phase 기반 분할 규칙, docs 저장 기준을 정의한다. 새 plans 작성, 기존 plans 체크오프, plans 기반 구현 작업 시 반드시 이 스킬을 따른다."
---

# Plans-Driven Workflow — 계획서 기반 구현 루틴

`AGENTS.md`의 plans 운영·구현 규칙을 실행 가능한 체크리스트로 정리한 운영 스킬.

## 기본 루프 (태스크 단위)

```
1. plans/*.md 읽고 다음 미체크 태스크 선택
2. 실제 코드와 태스크가 맞지 않으면 plans를 먼저 업데이트
3. 태스크 구현
4. 해당 검증 실행 (pytest / npm run test / npm run build)
5. 검증 통과 시 체크박스 `- [x]` 반영
6. 커밋 (type(scope): summary)
7. push
8. 다음 태스크로
```

**검증 실패 상태에서 커밋 금지.** 커밋 전에 반드시 검증 통과.

## 최소 검증 기준

| 변경 영역 | 검증 |
|----------|------|
| 백엔드 | `uv run pytest apps/backend/tests/<관련>.py -v` |
| 프론트 | `npm run lint` + 관련 `npm run test` (vitest) + `node --test` (mjs) |
| UI/빌드 영향 | `npm run build`까지 |
| 프롬프트/툴 정책 | 정책 테스트(`test_research_prompt_policy.py`, `test_agent_tools.py` 등) + supervisor/worker/validator 경로 영향 확인 |

## 커밋 컨벤션

형식: `type(scope): summary`

| type | 용도 |
|------|------|
| feat | 새 기능 |
| fix | 버그 수정 |
| refactor | 기능 변화 없는 구조 개선 |
| docs | 문서만 수정 (plans 체크오프 포함 가능) |
| test | 테스트만 |
| chore | 빌드/의존성/설정 |

scope 예시: `auth`, `threads`, `agent-core`, `plan`, `workflow`, `ui`, `tools`, `prompts`, `memory`, `dashboard`, `coding-team` 등

예:
- `feat(threads): add thread summary endpoint`
- `fix(auth): reject expired reset tokens`
- `refactor(agent-core): simplify supervisor routing`
- `docs(plan): check off patch service task`

**plan 체크 + 코드 변경이 같은 태스크면 같은 커밋에 포함 가능.**

## plans 문서 작성 규칙

### 상단 요약 블록 (필수)

```md
---
작업명: {Work Name}
간단요약: {한 문장}
작성일시: {YYYY-MM-DD HH:MM KST}
최종 수정일시: {YYYY-MM-DD HH:MM KST}
---
```

기존 plans에 블록이 없으면, 그 plans를 수정할 때 함께 보강.

### 본문 구조

- **목표 / 범위 / 전제 / 검증 방법**을 짧게
- 중간 규모 이상은 `Phase 1`, `Phase 2`, ... 단위로 분할
- 각 phase는 독립 구현·검증·체크·커밋 가능
- 각 phase 아래에 체크박스 태스크 나열

```md
## Phase 1. 데이터 모델 및 설정
- [ ] 모델 추가
- [ ] 환경변수 추가
- [ ] 기본 테스트 보강

## Phase 2. 서비스 및 API
- [ ] 서비스 레이어 구현
- [ ] 라우터 연결
- [ ] 인증/권한 테스트 추가
```

### 파일명 컨벤션

- 대문자 스네이크 케이스 + 목적 접미사: `*_PLAN.md`, `*_TODO.md`
- 안정화/운영 TODO는 `CURRENT_STABILIZATION_TODO.md`처럼 주제별 섹션 중심 허용
- 구현 순서 의존성 큰 작업은 phase 기반 분할 우선

## docs 저장 기준

조사/리서치/비교 분석 결과가 재사용 가치가 있을 때만 `docs/*.md` 저장:
- 조사 범위가 넓고 출처 여러 개
- 이후 설계/구현 판단의 근거로 재사용 가능
- 아키텍처 대안/기술 선택/운영 정책 등 장기 참조

단순 Q&A는 저장하지 않음. 저장 시 작성 시각, 요약/범위/핵심 결론/근거를 분리.

## 체크박스 반영 규칙

- 태스크 1개 완료 + 검증 통과 → 즉시 `- [x]` 반영
- 체크와 커밋 사이에 시간을 두지 않음
- 여러 태스크를 한 번에 배치 체크 금지 (추적성 저하)

## 불변 규칙

- 사용자가 이미 수정해 둔 영역은 되돌리지 않음
- 현재 작업과 무관한 수정은 혼입하지 않음
- plan 문서와 실제 코드가 다르면 구현 전에 plan을 먼저 업데이트

## 디버깅/안정화 작업

즉시성 높은 작업은 `plans/CURRENT_STABILIZATION_TODO.md` 주제별 섹션으로 관리 가능. 단, 여러 phase에 걸친 리팩토링은 별도 `*_PLAN.md` 생성.

## 체크리스트

- [ ] 해당 plans/*.md 상단 요약 블록 최신 상태?
- [ ] 태스크가 실제 코드 상태와 일치?
- [ ] 구현 → 검증 → 체크 → 커밋 순서 준수?
- [ ] 커밋 메시지가 `type(scope): summary` 형식?
- [ ] 관련 supervisor/worker/validator/테스트 경로 영향 확인?
- [ ] 작업 범위 외 수정이 혼입되지 않았음?
