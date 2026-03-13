# Phase 3: 고급 기능 도입 계획 (Advanced Features & HITL)

*참고: 본 문서는 [`@plans/HIERARCHICAL_MODERNIZATION_PLAN.md`](./HIERARCHICAL_MODERNIZATION_PLAN.md)의 **"Phase 3: 고급 기능 도입"**에 명시된 요구사항(HITL, 동적 도구 할당, 추적성 통합)을 풀스택 관점에서 구체화한 세부 실행 계획입니다.*

## 1. 개요 (Objective)
본 계획은 계층적 멀티 에이전트 아키텍처 현대화의 마지막 단계(Phase 3)로, Human-in-the-Loop(HITL), 동적 도구 할당, 그리고 심층 추적성 통합을 목표로 합니다.
특히 HITL은 단순히 백엔드에서 그래프를 중지하는 것에 그치지 않고, 프론트엔드 UI를 통해 사용자가 의사결정에 개입하고 피드백을 전달할 수 있는 **End-to-End 상호작용 구조**를 구축하는 데 중점을 둡니다.

## 2. 세부 구현 전략 (Implementation Strategy)

### 2.1. Human-in-the-Loop (HITL) 풀스택 연동
LangGraph 1.0+의 `interrupt()` 패턴을 활용하여 고위험 의사결정 시 사용자의 승인/반려/수정 지시를 받습니다.

*   **백엔드 (Backend & Agent Core):**
    *   `agent-core` 또는 `main_graph`에 명시적인 검토 노드(Review Node) 추가.
    *   Supervisor가 민감한 작업(예: 외부 시스템 배포, 결제, 최종 문서 확정 등)을 감지하면 `interrupt("Requires user approval")` 호출.
    *   그래프가 중지(Suspended) 상태가 되면 체크포인터에 상태를 저장.
    *   **신규 API 엔드포인트 (`/api/chat/resume`):** 클라이언트로부터 `thread_id`와 사용자의 결정(승인, 반려 및 피드백)을 전달받아 `graph.stream(Command(resume=user_feedback), thread_id=...)` 방식으로 그래프 실행을 재개.
*   **프론트엔드 (Next.js UI):**
    *   SSE 스트림에서 `status=interrupted` (또는 `requires_action`) 이벤트를 수신하도록 `chat.py` 및 `page.tsx` 확장.
    *   UI 상에 **"Action Required (사용자 개입 필요)" 컴포넌트** 렌더링.
    *   사용자에게 [승인(Approve)], [반려(Reject)], [수정 요청(Provide Feedback)] 버튼과 입력 필드 제공.
    *   선택 결과를 신규 Resume API로 전송하고 스트리밍을 이어나감.

### 2.2. 동적 도구 할당 (Dynamic Tool Assignment)
*   현재 워커들은 미리 하드코딩된 도구(`tools=[...]`)만 사용 중입니다.
*   작업의 맥락에 따라 Supervisor가 워커에게 전달할 도구 목록을 동적으로 변경하거나, "필요한 경우 특정 도구를 추가로 요청"할 수 있는 권한 부여 로직을 구현합니다.
*   `TeamBuilder`가 요청 시마다 런타임에 `tools` 목록을 확장하여 워커 노드를 동적으로 구성(또는 `bind_tools` 동적 갱신)할 수 있도록 구조 고도화.

### 2.3. 추적성 및 지휘 체계 통합 (Traceability Integration)
*   이미 도입된 `route_history`와 `trace_service`를 더욱 융합.
*   "어떤 Supervisor가 $\rightarrow$ 어떤 이유로(reasoning) $\rightarrow$ 어떤 팀을 호출했고 $\rightarrow$ 그 결과 Validator가 어떻게 평가했는지"에 대한 전체 트리를 UI 상의 **Live Trace** 패널에서 시각적으로 명확하게 계층화하여 표현.

## 3. 구현 단계 (Execution Steps)

- [x] **Step 1: Resume API 및 SSE 이벤트 확장**
  - `apps/backend/api/routes/chat.py`에 `/api/chat/resume` 라우트 생성.
  - 스트림 응답 시 `interrupt` 예외를 포착하여 클라이언트에 `interrupted` 이벤트 송출.
- [x] **Step 2: 프론트엔드 HITL UI 구현**
  - `apps/frontend/src/app/page.tsx`에 개입(Interrupt) 상태 관리 추가.
  - 대화 버블 내부에 승인/피드백 폼 UI 컴포넌트 개발.
- [x] **Step 3: Head Supervisor의 인터럽트 로직 적용**
  - `apps/backend/workflow/main_graph.py`에 특정 플래그나 상황에서 `interrupt()`를 발생시키는 Reviewer 노드 혹은 로직 연동.
- [x] **Step 4: 동적 도구 프로비저닝 (Dynamic Tools)**
  - `agent_core/builder.py` 수정 및 테스트 추가.

## 4. 기대 효과 (Definition of Done)
- 사용자는 최종 답변을 받기 전, 치명적인 동작에 대해 UI 버튼을 눌러 승인하거나 추가 피드백을 줄 수 있어야 합니다.
- 피드백 제공 시, 에이전트는 이를 수용하여 기존 작업을 재수행(`self-correction`)한 뒤 다시 결과를 제시합니다.
- 복잡도에 맞추어 유연하게 툴이 할당되고 이 모든 과정이 Trace에 남습니다.
