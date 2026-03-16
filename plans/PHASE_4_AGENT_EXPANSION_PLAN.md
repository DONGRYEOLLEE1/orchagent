# Phase 4: 추천 에이전트 및 팀 역할 확장 계획 (Agent Expansion Plan)

본 문서는 `docs/RECOMMENDED_AGENTS.md`의 제안 중 "아키텍처 고도화를 위한 필수 에이전트 (Core Architectural Agents)" 부분을 바탕으로 OrchAgent의 아키텍처를 고도화하기 위한 구체적인 실행 계획입니다. (도메인 특화 팀 확장은 제외됨)

## 1. 개요 및 목표
*   **목표:** 단순한 다중 에이전트 구성을 넘어, 복잡한 태스크를 계획(Planning) 및 검토(Review/Critic)할 수 있는 고도화된 아키텍처로 진화하며, 시스템 보호를 위한 수문장(Guardrail)을 추가합니다.
*   **로드맵 단계:**
    1.  **Phase 4.1:** Planner Agent 도입 (Head Supervisor 앞단의 작업 분해 및 계획 수립)
    2.  **Phase 4.2:** Reviewer/Critic Agent 격상 (Validator 노드 고도화)
    3.  **Phase 4.3:** Guardrail Node 도입 (입출력 보안 및 정책 검증)

---

## 2. 세부 구현 목표 (Todo List)

### Phase 4.1: Planner Agent 도입 (Architecture Upgrade)
사용자의 복잡한 요구사항을 실행 가능한 하위 태스크(DAG 구조)로 분해하는 플래닝 단계를 추가합니다.

*   **[ ] 상태(State) 스키마 변경**
    *   [ ] `packages/agent-core/src/agent_core/state.py`에 `task_plan` (또는 `plan`) 필드 추가 (List 또는 Dict 형태로 태스크 상태 추적).
*   **[ ] Planner 노드 구현**
    *   [ ] 사용자의 입력 직후 실행되는 `Planner` 노드 생성.
    *   [ ] 복잡도를 판단하여 단순 질의는 바로 `Head Supervisor`로 넘기고, 복잡한 요청은 Markdown 기반의 실행 계획을 생성하여 `task_plan` 상태에 저장.
*   **[ ] Head Supervisor 로직 고도화**
    *   [ ] `Head Supervisor`가 매 턴마다 `task_plan`을 참조하여 다음 스텝을 어느 팀에 할당할지 결정하도록 프롬프트/로직 수정.
    *   [ ] 태스크 완료 시 `task_plan`의 상태를 업데이트(Check)하는 메커니즘 구현.

### Phase 4.2: Reviewer/Critic Agent 고도화
기존의 단순 규칙 기반(혹은 단일 Prompt 기반) Validator를 심층 비평이 가능한 구조로 발전시킵니다.

*   **[ ] Reviewer 모델 정의**
    *   [ ] `packages/agent-core/src/agent_core/validator.py`를 리팩토링 혹은 분리하여, 단순 성공/실패 여부 판단이 아닌 구체적인 누락 사항, 할루시네이션, 논리 오류를 비평하는 `Reviewer` 시스템 프롬프트 적용.
*   **[ ] 피드백 사이클 강화**
    *   [ ] Reviewer의 상세한 피드백이 해당 워커나 팀 수퍼바이저에게 명확히 전달되도록 메시지 구조 강화.
    *   [ ] 너무 많은 피드백 루프에 빠지지 않도록 횟수 제한(이미 구현된 Edge Case 1)과 연계.

### Phase 4.3: Guardrail Node 도입 (Security & Compliance)
Worker Agent 형태가 아닌 빠르고 결정론적인 Node/Middleware 형태로 구축하여 시스템의 입출력을 보호합니다.

*   **[ ] Input Guardrail (입력 수문장)**
    *   [ ] 사용자의 프롬프트 인젝션(Jailbreak), 욕설, 시스템 목적(코딩/분석) 외의 질문을 차단하는 노드 생성.
    *   [ ] `main_graph.py`의 진입점(`START`) 직후에 배치하여, 통과 시 Planner로 전달하고 실패 시 즉시 에러 반환.
*   **[ ] Output Guardrail (출력 수문장)**
    *   [ ] 최종 응답에 PII(개인정보), 민감한 사내 데이터가 포함되었는지 정규식 또는 가벼운 LLM 호출로 검증.
    *   [ ] 완료 노드(`__end__`) 직전에 배치하여, 정책 위반 시 마스킹(Masking) 처리하거나 차단.

---

## 3. 테스트 및 검증 계획 (QA)
*   **[ ] Integration Tests:** Planner가 정상적으로 계획을 수립하고, Head Supervisor가 이를 따라 워커들에게 작업을 분배하는 전체 사이클 검증.
*   **[ ] Subgraph/Validator Tests:** Reviewer Agent가 산출물의 오류를 정확히 지적하고 루프를 통해 개선되는지 검증.
*   **[ ] Guardrail Tests:** 악의적인 프롬프트 입력 시 즉각 차단되는지, 출력에 포함된 민감 정보가 마스킹 처리되는지 검증.
*   **[ ] Edge Cases:** 너무 복잡한 계획으로 인한 무한 루프, 비평가의 과도한 태클(Critic Hallucination) 방지 기믹 동작 여부 확인.
