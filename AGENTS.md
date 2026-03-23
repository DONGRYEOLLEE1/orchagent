# AGENTS.md

## 목적

이 문서는 `orchagent` 저장소에서 작업하는 에이전트를 위한 운영 가이드다. 이 저장소는 `uv` 워크스페이스 기반의 Python 백엔드와 `npm` 기반의 Next.js 프런트엔드로 구성된 모노레포이며, 핵심 멀티 에이전트 오케스트레이션 코드는 `apps/backend`, `packages/agent-core`, `packages/agent-tools`, `packages/prompt-kit`에 분리되어 있다.

## 저장소 개요

- `apps/backend`: FastAPI, LangGraph, SQLAlchemy 기반 백엔드
- `apps/frontend`: Next.js 16, React 19 기반 UI
- `packages/agent-core`: supervisor, validator, team builder, state 등 오케스트레이션 코어
- `packages/agent-tools`: 웹 조사, 파일 I/O, 비전 도구
- `packages/prompt-kit`: 시스템 프롬프트와 워커 프롬프트의 단일 관리 지점
- `plans`: 기능 추가, 강화, 리팩토링을 위한 상세 계획서
- `docs`: 조사/연구 결과, 아키텍처 메모, 재사용 가치가 있는 분석 문서
- `infra`: Docker Compose 및 개발 스크립트

## 기본 실행 명령

### 백엔드

```bash
cd apps/backend
uv sync
uv run uvicorn main:app --reload --port 8002
uv run pytest tests/ -v
```

### 프런트엔드

```bash
cd apps/frontend
npm install
npm run dev
npm run lint
npm run test
```

### 전체 스택

```bash
./infra/scripts/start-dev.sh
```

## 필수 아키텍처 규칙

- 실제 런타임 LLM 초기화는 반드시 `langchain.chat_models.init_chat_model`을 사용한다.
- worker agent 초기화는 반드시 `langchain.agents.create_agent`를 사용한다.
- `langgraph.prebuilt.create_react_agent`는 절대 사용하지 않는다.
- 모든 시스템 프롬프트와 워커 프롬프트는 반드시 `packages/prompt-kit` 패키지 내부에서 관리한다.
- 애플리케이션 코드나 워크플로우 코드에 시스템 프롬프트 문자열을 하드코딩하지 않는다.
- 프롬프트를 추가하거나 수정할 때는 우선 `packages/prompt-kit/src/prompt_kit/` 아래에 정의하고, 다른 패키지에서는 import 해서 사용한다.

현재 코드베이스 기준 참조 위치:

- LLM 초기화: `apps/backend/workflow/main_graph.py`
- worker agent 생성: `packages/agent-core/src/agent_core/builder.py`
- 프롬프트 정의: `packages/prompt-kit/src/prompt_kit/prompts.py`

## plans 폴더 운영 규칙

- `plans` 폴더는 구체적인 리팩토링, 기능 추가, 기능 강화 작업을 위한 마크다운 계획서 저장소다.
- 새 `plans/*.md` 파일을 만들거나 기존 계획서를 크게 갱신할 때는 문서 상단에 반드시 작성 날짜와 시각을 남긴다.
- 권장 표기:

```md
작성일시: 2026-03-23 16:30 KST
최종 수정일시: 2026-03-23 16:30 KST
```

- 기존 계획서에 타임스탬프가 없다면, 해당 파일을 수정하는 시점에 함께 보강한다.
- 각 계획서는 목표, 범위, 전제, 검증 방법을 짧게 적고, 실제 구현 단위별 태스크를 체크리스트로 나눠야 한다.
- 중간 규모 이상 기능 추가나 리팩토링 계획서는 가능한 한 `Phase 1`, `Phase 2`, `Phase 3`처럼 단계적으로 구현 가능한 구조로 나눈다.
- 각 phase는 독립적으로 구현, 검증, 체크 업데이트, 커밋이 가능한 단위여야 한다.
- 각 phase 아래에는 해당 단계에서 끝내야 할 세부 태스크를 체크리스트로 배치한다.
- 즉시성 높은 안정화 작업이나 운영 TODO는 `plans/CURRENT_STABILIZATION_TODO.md`처럼 주제별 섹션 중심으로 관리해도 되지만, 구현 순서 의존성이 큰 작업은 `plans/SIGNUP_AUTH_SYSTEM_PLAN.md` 같은 상세 계획서처럼 phase 기반 분할을 우선한다.
- 체크리스트는 반드시 순차적인 실행 단위로 쪼갠다. 예시:

```md
- [ ] 상태 스키마 확장
- [ ] supervisor 라우팅 로직 수정
- [ ] 관련 테스트 추가 및 통과 확인
```

- phase 기반 권장 예시:

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

- 파일명은 기존 저장소 관례를 따라 가능하면 대문자 스네이크 케이스와 목적 접미사(`*_PLAN.md`, `*_TODO.md`)를 사용한다.

## plans 기반 구현 작업 규칙

`plans/*.md`를 근거로 코드 수정을 진행할 때는 아래 절차를 따른다.

1. 구현 전에 계획서를 읽고 실제 코드와 맞지 않는 태스크가 있으면 먼저 계획서를 업데이트한다.
2. 태스크 1개를 완료할 때마다 관련 검증을 수행한다.
3. 검증이 끝나면 해당 체크리스트를 즉시 `- [x]`로 반영한다.
4. 체크 반영 직후 커밋한다.
5. 커밋 직후 원격으로 push 한다.
6. 다음 태스크로 넘어간다.

추가 규칙:

- plan 문서 변경과 코드 변경이 같은 태스크에 속하면 같은 커밋에 포함해도 된다.
- 커밋 메시지는 반드시 commit-convention을 따른다.
- 권장 형식은 `type(scope): summary` 이다.
- 권장 타입 예시: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- 예시:
  - `feat(threads): add thread summary endpoint`
  - `fix(auth): reject expired reset tokens`
  - `refactor(agent-core): simplify supervisor routing`
  - `docs(plan): check off patch service task`

## docs 폴더 운영 규칙

- 사용자가 조사, 리서치, 비교 분석, 기술 검토를 지시했을 때 결과가 일회성 답변을 넘어 재사용 가치가 있다고 판단되면 `docs` 폴더에 마크다운으로 정리한다.
- 다음 중 하나에 해당하면 `docs` 저장을 우선 검토한다.
  - 조사 범위가 넓고 출처가 여러 개인 경우
  - 이후 설계나 구현 판단의 근거 문서로 재사용될 가능성이 큰 경우
  - 아키텍처 대안, 기술 선택, 운영 정책처럼 장기 참조 가치가 있는 경우
- 단순 Q&A 수준이거나 일회성 응답이면 굳이 `docs` 파일을 만들지 않는다.
- `docs/*.md`도 가능하면 작성 시각을 상단에 남긴다.
- 문서는 요약, 범위, 핵심 결론, 근거를 명확히 분리해서 작성한다.
- 파일명은 기존 관례를 따라 가능하면 대문자 스네이크 케이스를 사용한다.

## 구현 및 검증 원칙

- 백엔드 변경 시 우선 `apps/backend/tests` 아래 관련 `pytest` 테스트를 추가하거나 갱신한다.
- 프런트엔드 변경 시 `npm run lint`와 관련 테스트를 우선 확인한다.
- 루트 워크스페이스는 `uv`로 관리되므로 Python 의존성은 개별 `pip install`보다 `uv sync` 기준으로 맞춘다.
- 사용자 변경분이 이미 존재할 수 있으므로, 현재 작업과 무관한 수정은 되돌리지 않는다.
- 프롬프트 정책을 바꿀 때는 프롬프트 텍스트만 바꾸지 말고, 그 프롬프트를 소비하는 supervisor/worker/validator 경로와 테스트 영향까지 함께 확인한다.
