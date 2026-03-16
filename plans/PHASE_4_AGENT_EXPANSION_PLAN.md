# Phase 4: 추천 에이전트 및 팀 역할 확장 계획 (Agent Expansion Plan)

본 문서는 `docs/RECOMMENDED_AGENTS.md`의 제안을 바탕으로 OrchAgent의 아키텍처를 고도화하고 신규 도메인 특화 에이전트를 도입하기 위한 구체적인 실행 계획입니다.

## 1. 개요 및 목표
*   **목표:** 단순한 Research, Writing 구성을 넘어, 데이터 분석(Data Analytics) 능력을 부여하고, 복잡한 태스크를 계획(Planning) 및 검토(Review)할 수 있는 아키텍처로 진화합니다.
*   **로드맵 단계:**
    1.  **Phase 4.1:** Data Analytics Team 신설 (데이터 엔지니어 및 분석가 도입)
    2.  **Phase 4.2:** Planner Agent 도입 (Head Supervisor 앞단의 작업 분해 및 계획 수립)
    3.  **Phase 4.3:** Reviewer/Critic Agent 격상 (Validator 노드 고도화)
    4.  **Phase 4.4:** Web Operations Team 신설 (브라우저 자동화 및 동적 스크래핑)

---

## 2. 세부 구현 목표 (Todo List)

### Phase 4.1: Data Analytics Team 도입 (Quick Win)
데이터 분석 및 시각화를 위한 독립적인 팀과 워커를 추가합니다. Python REPL 도구를 활용하여 실제 데이터를 처리하고 차트를 생성하는 기능을 구현합니다.

*   **[ ] 패키지 및 도구 설정**
    *   [ ] `packages/agent-tools`에 `DataAnalysisTools` 모듈 생성 (Python 코드 실행 환경 구축 등).
    *   [ ] 보안을 위해 샌드박스화된 환경 혹은 안전한 Python 실행 도구 통합 검토.
*   **[ ] Data Analytics 팀 서브그래프 (`apps/backend/workflow/teams/analytics.py`) 구현**
    *   [ ] `Data Engineer` 워커 추가 (데이터 추출 및 전처리 특화 프롬프트/도구 부여).
    *   [ ] `Data Analyst` 워커 추가 (통계 분석 및 시각화 코드 작성 특화 프롬프트/도구 부여).
    *   [ ] `TeamBuilder`를 이용해 팀 내부 통신 및 Supervisor 구축.
*   **[ ] Head Supervisor 라우팅 및 연동**
    *   [ ] `main_graph.py`의 메인 그래프에 `analytics_team` 노드 등록.
    *   [ ] `Head Supervisor` 시스템 프롬프트 업데이트 (데이터 관련 질문 시 analytics_team으로 라우팅).

### Phase 4.2: Planner Agent 도입 (Architecture Upgrade)
사용자의 복잡한 요구사항을 실행 가능한 하위 태스크(DAG 구조)로 분해하는 플래닝 단계를 추가합니다.

*   **[ ] 상태(State) 스키마 변경**
    *   [ ] `packages/agent-core/src/agent_core/state.py`에 `task_plan` (또는 `plan`) 필드 추가 (List 또는 Dict 형태로 태스크 상태 추적).
*   **[ ] Planner 노드 구현**
    *   [ ] 사용자의 입력 직후 실행되는 `Planner` 노드 생성.
    *   [ ] 복잡도를 판단하여 단순 질의는 바로 `Head Supervisor`로 넘기고, 복잡한 요청은 Markdown 기반의 실행 계획을 생성하여 `task_plan` 상태에 저장.
*   **[ ] Head Supervisor 로직 고도화**
    *   [ ] `Head Supervisor`가 매 턴마다 `task_plan`을 참조하여 다음 스텝을 어느 팀에 할당할지 결정하도록 프롬프트/로직 수정.
    *   [ ] 태스크 완료 시 `task_plan`의 상태를 업데이트(Check)하는 메커니즘 구현.

### Phase 4.3: Reviewer/Critic Agent 고도화
기존의 단순 규칙 기반(혹은 단일 Prompt 기반) Validator를 심층 비평이 가능한 구조로 발전시킵니다.

*   **[ ] Reviewer 모델 정의**
    *   [ ] `packages/agent-core/src/agent_core/validator.py`를 리팩토링 혹은 분리하여, 단순 성공/실패 여부 판단이 아닌 구체적인 누락 사항, 할루시네이션, 논리 오류를 비평하는 `Reviewer` 시스템 프롬프트 적용.
*   **[ ] 피드백 사이클 강화**
    *   [ ] Reviewer의 상세한 피드백이 해당 워커나 팀 수퍼바이저에게 명확히 전달되도록 메시지 구조 강화.
    *   [ ] 너무 많은 피드백 루프에 빠지지 않도록 횟수 제한(이미 구현된 Edge Case 1)과 연계.

### Phase 4.4: Web Operations Team 신설 (Expansion)
동적 페이지 스크래핑 및 실제 브라우저 제어가 가능한 팀을 구성합니다. (기존 HITL 기능과 연계)

*   **[ ] 브라우저 자동화 도구 통합**
    *   [ ] Selenium, Playwright 또는 Browser Use 등 적합한 프레임워크 선정 및 `agent-tools`에 연동.
*   **[ ] Web Operations 팀 서브그래프 (`apps/backend/workflow/teams/web_ops.py`) 구현**
    *   [ ] `Browser Navigator` 워커 추가 (클릭, 폼 입력 등).
    *   [ ] `Scraper` 고도화 (동적 데이터 렌더링 후 스크래핑).
*   **[ ] HITL (Human-in-the-Loop) 적용 검토**
    *   [ ] 결제, 예약 등 Side-effect가 발생하는 주요 액션 전에 사용자 승인을 받도록 `requires_approval` 플래그 활용.

---

## 3. 테스트 및 검증 계획 (QA)
*   **[ ] Unit Tests:** 각 신규 도구(Python REPL 등)에 대한 단위 테스트 작성.
*   **[ ] Subgraph Tests:** `test_team_subgraphs.py`에 Analytics Team, Web Ops Team 등록 여부 확인.
*   **[ ] Integration Tests:** Planner가 정상적으로 계획을 수립하고, Head Supervisor가 이를 따라 워커들에게 작업을 분배하는 전체 사이클 검증.
*   **[ ] Edge Cases:** Python 실행 중 무한 루프, 문법 에러, 샌드박스 우회 시도(보안) 등의 예외 상황 테스트.
