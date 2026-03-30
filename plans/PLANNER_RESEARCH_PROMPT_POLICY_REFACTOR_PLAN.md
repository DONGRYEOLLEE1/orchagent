---
작업명: Planner Research Prompt Policy Refactor Plan
간단요약: planner와 research team의 프롬프트 계약을 재정렬해 불필요한 handoff, worker-tool mismatch, research routing 불안정을 줄인다.
작성일시: 2026-03-30 17:56 KST
최종 수정일시: 2026-03-30 18:04 KST
---

# Planner / Research Prompt Policy Refactor Plan

## 배경

현재 코드베이스에서 `planner`, `research_team`, `head supervisor` 정책을 함께 보면 프롬프트 철학은 나쁘지 않지만, 실제 실행 계약이 서로 어긋나는 지점이 분명하다.

핵심 문제는 다음 4가지다.

- `research_team`이 전용 team supervisor 정책 없이 generic team supervisor를 그대로 사용한다.
- `search`와 `web_scraper`가 동일한 `RESEARCHER_PROMPT`를 공유하는데, 실제 tool capability는 서로 다르다.
- planner 휴리스틱은 단순 research Q&A를 `research_team -> writing_team`으로 강제하지만, head supervisor prompt는 `research -> finalizer`를 선호한다.
- research worker prompt는 “최신성”과 “출처 인용”을 요구하지만, source quality/date verification 같은 운영 규칙은 충분히 구체적이지 않다.

즉 이번 작업의 핵심은 프롬프트 문구를 조금 손보는 것이 아니라, `planner / supervisor / research worker / research team supervisor` 간의 역할 계약을 다시 맞추는 것이다.

## 목표

- research team에 전용 supervisor policy를 도입한다.
- `search`와 `web_scraper`에 서로 다른 worker prompt를 부여한다.
- 단순 research-answer 경로에서 `writing_team` handoff를 기본값으로 강제하지 않도록 planner 정책을 수정한다.
- 최신성/출처/스크래핑 근거 규칙을 research worker prompt에 더 구체적으로 반영한다.
- prompt 변경이 실제 라우팅, SSE, finalizer 경로에 미치는 회귀를 테스트로 봉합한다.

## 범위

- 포함
  - `packages/prompt-kit` 내 planner/research 관련 prompt 개편
  - research team 전용 supervisor prompt 추가
  - `apps/backend/workflow/teams/research.py`의 worker prompt 분리
  - `planner.py` 휴리스틱과 prompt contract 정리
  - research / planner / supervisor 관련 테스트 보강
- 제외
  - research team tool 자체 교체
  - citation renderer 전면 재설계
  - Tavily / scraper tool 구현 변경
  - writing team 전용 supervisor policy 추가

## 현재 설계 문제 요약

### 1. Research Team 전용 ordering 계약이 없다

- generic `TEAM_SUPERVISOR_PROMPT`는 “무엇이 남았는지”만 말하고, research team의 자연스러운 `search -> scrape -> finish` 순서를 강제하지 않는다.
- 따라서 `web_scraper`가 URL 없이 먼저 호출되거나, 누가 최종 research summary를 책임지는지 모호해질 수 있다.

### 2. Worker prompt와 tool capability가 맞지 않는다

- `RESEARCHER_PROMPT`는 한 worker가 query formulation, search, scrape, synthesis를 다 수행할 수 있다는 전제로 쓰여 있다.
- 실제로는 `search`는 Tavily만, `web_scraper`는 scrape만 가능하다.
- 이 mismatch는 도구 호출 실패와 불필요한 라우팅 재시도를 유발할 수 있다.

### 3. Planner와 Head Supervisor가 서로 다른 기본 전략을 밀고 있다

- planner 휴리스틱은 단순 research request를 거의 자동으로 `research_team -> writing_team`으로 만든다.
- 하지만 head supervisor policy는 간단한 research-answer는 `research_team` 한 번 후 final synthesis로 끝내는 것을 선호한다.
- 이 충돌은 불필요한 `writing_team` handoff를 만들 수 있다.

### 4. 최신성/출처 규칙이 운영 수준으로는 약하다

- 현재 research prompt는 “up-to-date”, “cite sources”만 말한다.
- publish date 비교, 1차 출처 우선, snippet-only 응답 금지, scrape evidence 우선 같은 규칙이 없다.

## 설계 원칙

### 1. Research Team은 순서가 있는 팀으로 본다

- 기본 순서:
  - `search`
  - `web_scraper`
  - `FINISH`
- 단, search 결과만으로 충분하고 scrape 필요가 없을 때만 early finish를 허용한다.

### 2. Worker prompt는 capability-aligned여야 한다

- `search` worker는 query formulation + result selection + candidate URL handoff에 집중한다.
- `web_scraper` worker는 주어진 URL evidence를 읽고 factual extraction에 집중한다.
- 한 worker에게 자신이 할 수 없는 행동을 요구하지 않는다.

### 3. Planner는 불필요한 team handoff를 만들지 않는다

- 단순 research-answer 요청의 기본 2단계는 아래가 되어야 한다.
  1. `[research_team]` 필요한 evidence 수집
  2. `final synthesis`
- `writing_team`은 아래 경우에만 기본 플랜에 들어간다.
  - 보고서/문서/초안/아티클/슬라이드 같은 산출물이 명시됨
  - 구조화된 outline/doc artifact 생성이 명시적으로 필요함

### 4. 최신성은 worker prompt 안에서 operationalize 한다

- “최신” 요청이면 publish date와 source recency를 언급하게 한다.
- 가능하면 1차 출처 또는 직접 기사/문서 본문 근거를 우선한다.
- search snippet만으로 결론내리지 않게 한다.

## 권장 구현 방향

### Prompt Kit

- `RESEARCH_TEAM_SUPERVISOR_PROMPT` 추가
- `SEARCH_WORKER_PROMPT` 추가
- `WEB_SCRAPER_PROMPT` 추가
- `PLANNER_PROMPT`에서 simple research-answer 기본 전략을 `research -> final synthesis` 쪽으로 정렬
- 필요 시 `SYSTEM_SUPERVISOR_PROMPT`의 “fewest handoffs” 조항과 wording를 planner와 더 명시적으로 맞춤

### Runtime Wiring

- `apps/backend/workflow/teams/research.py`
  - `search`에 `SEARCH_WORKER_PROMPT`
  - `web_scraper`에 `WEB_SCRAPER_PROMPT`
  - team builder에 `RESEARCH_TEAM_SUPERVISOR_PROMPT`
- `packages/agent-core/src/agent_core/nodes/planner.py`
  - `_build_simple_research_plan()`이 기본적으로 `writing_team`을 넣지 않도록 수정

### Test Strategy

- planner 휴리스틱이 simple research-answer에 대해 `writing_team`을 강제하지 않는지 검증
- research team supervisor가 `search`를 먼저 고르는지 검증
- scrape가 필요한 경우에만 `web_scraper`로 넘어가는지 검증
- worker prompt 분리 후에도 existing research flow 테스트가 깨지지 않는지 확인

## 검증 방법

- 백엔드 최소 검증
  - `uv run pytest apps/backend/tests/test_planner.py -v`
  - `uv run pytest apps/backend/tests/test_supervisor.py -v`
  - `uv run pytest apps/backend/tests/test_team_subgraphs.py -v`
  - `uv run pytest apps/backend/tests/test_workflow_graph.py -v`
  - research prompt 분리용 테스트 파일을 추가했다면 해당 파일 포함

## Phase 1. Research Team Contract Split

- [x] research 전용 supervisor prompt와 worker별 분리 prompt를 `packages/prompt-kit`에 추가하고, `apps/backend/workflow/teams/research.py`가 새 계약을 사용하도록 연결한다.
- [x] research prompt split과 search-first / scrape-second ordering을 검증하는 테스트를 추가하거나 확장한다.

## Phase 2. Planner Policy Alignment

- [x] `PLANNER_PROMPT`와 `planner.py` 휴리스틱을 수정해 simple research-answer 기본 전략을 `research -> final synthesis`로 정렬하고, writing deliverable이 명시된 경우에만 `writing_team`이 들어가도록 재정의한다.
- [x] planner 관련 회귀 테스트를 보강해 canonical team token과 lightweight planning 조건을 검증한다.

## Phase 3. Supervisor Consistency and Regression

- [x] `SYSTEM_SUPERVISOR_PROMPT`와 research 전용 supervisor prompt의 책임 경계를 정리하고, head supervisor가 research evidence만으로 충분한 경우 finalizer로 자연스럽게 넘어가는지 관련 테스트를 추가한다.
- [x] workflow/team wiring 테스트를 보강해 research team prompt wiring이 유지되는지 검증한다.

## Phase 4. Hardening and Evaluation

- [ ] 최신성/source-quality 규칙, unnecessary `writing_team` handoff 감소, existing SSE/finalizer 계약 유지까지 포함한 회귀 테스트를 추가하고 전체 관련 테스트를 통과시킨다.

## 완료 기준

- research team이 generic team router가 아니라 research-specific contract를 가진다.
- `search`와 `web_scraper`의 prompt가 capability-aligned 상태가 된다.
- simple research-answer 요청에서 planner가 기본적으로 `writing_team`을 강제하지 않는다.
- prompt 변경이 supervisor/finalizer/workflow 테스트에서 회귀 없이 통과한다.
