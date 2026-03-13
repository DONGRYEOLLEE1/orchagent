# Backend QA Test Plan (Edge Cases & Coverage)

본 문서는 OrchAgent 백엔드(`apps/backend/tests/`)의 최신 코드베이스(Phase 1~3: 네이티브 서브그래프, 검증자 노드, HITL 인터럽트, 동적 도구 프로비저닝)를 기반으로 하여, QA Engineer 관점에서 시스템의 견고함을 확보하기 위한 **테스트 추가 및 변경 계획**을 정리한 것입니다.
특히 정상 경로(Happy Path) 외에 시스템이 예기치 못한 입력이나 상태에서 어떻게 우아하게 실패하거나 복구하는지(Edge Cases)에 집중합니다.

## 1. 개요
*   **현재 상태:** `test_api.py`, `test_supervisor.py`, `test_dynamic_tools.py` 등에 기본적인 정상 작동 테스트는 확보되어 있으나, 새로운 구조(Validator, HITL Resume, Dynamic Model)에 대한 비정상 경로 테스트가 부족합니다.
*   **목표:** 각 핵심 컴포넌트별로 발생할 수 있는 극단적 상황(Edge Cases)을 정의하고, 이를 검증할 테스트 케이스를 설계합니다.

---

## 2. 컴포넌트별 테스트 계획 (Test Scenarios)

### 2.1. Validator & Self-Correction Loop (검증자 및 자가 수정)
**대상 파일:** `test_supervisor.py` (또는 신규 `test_validator.py`)
현재는 Validator가 '유효하지 않음'을 반환할 때 Supervisor가 다시 워커에게 라우팅하는 기본 로직만 있습니다.

*   **[ ] Edge Case 1: 무한 자가 수정 루프 방지 (Infinite Correction Loop)**
    *   **시나리오:** 워커가 계속해서 잘못된 답을 내놓아 Validator가 계속해서 `is_valid=False`를 반환하는 상황.
    *   **검증 목표:** `remaining_steps` 혹은 재시도 횟수 제한 기믹이 동작하여, 그래프가 무한 루프에 빠지지 않고 적절히 중단(`errored` 또는 `completed` with warning)되는지 확인.
*   **[ ] Edge Case 2: Validator의 환각 (Validator Hallucination)**
    *   **시나리오:** Validator 자체가 구조화된 출력(Structured Output)을 반환하지 못하거나 파싱 에러(Pydantic Validation Error)를 일으키는 상황.
    *   **검증 목표:** 파싱 에러 발생 시 시스템이 패닉에 빠지지 않고 기본값(예: 통과 처리 또는 특정 에러 메시지와 함께 Supervisor 반환)으로 안전하게 롤백되는지 확인.

### 2.2. Human-in-the-Loop (HITL) Resume API
**대상 파일:** `test_api.py`
현재는 `approve` 와 `feedback`을 통한 정상 재개만 테스트하고 있습니다.

*   **[ ] Edge Case 3: 유효하지 않은 Thread ID로 Resume 시도**
    *   **시나리오:** 클라이언트가 존재하지 않거나 이미 완료된 `thread_id`로 `/api/chat/resume`을 호출.
    *   **검증 목표:** API가 404 Not Found 또는 400 Bad Request를 반환하고, 빈 스트림이나 엉뚱한 노드 실행을 방지하는지 확인.
*   **[ ] Edge Case 4: 인터럽트 상태가 아닌데 Resume 호출**
    *   **시나리오:** 그래프가 `interrupt` 상태에 빠지지 않고 단순히 `running` 중이거나 `idle` 상태일 때 `Command(resume=...)`가 주입되는 상황.
    *   **검증 목표:** LangGraph 엔진 수준에서 발생하는 에러를 우아하게 잡아내어 프론트엔드에 `errored` 스트림 이벤트를 명확히 전달하는지 확인.
*   **[ ] Edge Case 5: 악의적인 피드백 페이로드**
    *   **시나리오:** `feedback` 필드에 시스템 프롬프트 인젝션 공격 문자열이나 비정상적으로 긴(수십 MB) 문자열이 주입된 상황.
    *   **검증 목표:** `ResumeRequest` 스키마 또는 내부 처리 과정에서 적절한 길이 제한 및 새니타이징(Sanitizing) 처리가 동작하는지(또는 안전하게 Truncate 되는지) 확인.

### 2.3. Dynamic Tool Provisioning (동적 도구 할당)
**대상 파일:** `test_dynamic_tools.py`
`active_tools`를 기반으로 도구를 할당하는 기본 기능은 확보되었습니다.

*   **[ ] Edge Case 6: 존재하지 않는 도구 이름 주입**
    *   **시나리오:** `state["active_tools"]` 리스트에 현재 워커에 아예 등록되지 않은(매핑되지 않은) 엉뚱한 도구 이름(예: `["delete_database", "hack_system"]`)이 포함된 상태로 할당 시도.
    *   **검증 목표:** `dynamic_model` 래퍼가 등록된 `tools` 풀 내에서만 안전하게 필터링하여 빈 도구 리스트 또는 유효한 도구만 바인딩하고 크래시가 나지 않는지 확인.
*   **[ ] Edge Case 7: 도구 리스트가 완전히 비워진 경우의 ReAct Agent**
    *   **시나리오:** 필터링 결과 `tools_to_bind`가 비어버린 경우.
    *   **검증 목표:** `create_react_agent`가 도구 바인딩 없이 순수 LLM(`return self.llm`)으로 동작할 때, 내부 루프가 에러 없이 정상적으로 종료 노드(`__end__`)에 도달하는지 확인.

### 2.4. SSE Stream Parsing & Tracing
**대상 파일:** `test_trace_service.py` / `test_api.py`

*   **[ ] Edge Case 8: 극단적으로 짧은 연결 끊김 (Client Disconnect)**
    *   **시나리오:** LLM이 응답을 스트리밍하는 도중에 클라이언트(프론트엔드)가 연결을 강제로 끊어버린 상황.
    *   **검증 목표:** 서버에 Broken Pipe 에러가 발생하더라도, 그 시점까지의 `trace_events`가 유실되지 않고 `finally` 블록을 통해 DB에 배치 저장(Batch Save)되는지 확인.

---

## 3. 실행 전략 (Next Steps)
1.  위 시나리오 중 우선순위가 높은 **Validator 루프 검증(Edge 1)**과 **HITL 비정상 상태 재개(Edge 4)** 테스트 케이스부터 작성을 시작합니다.
2.  에러 발생 시 프론트엔드에 전달되는 SSE 계약 스키마가 깨지지 않는지 지속 확인합니다.
3.  필요 시 Pytest의 `pytest-asyncio` 및 `httpx`의 비동기 Mocking을 활용하여 예외 상황을 강제 주입(Inject)합니다.
## 4. 백엔드 QA Edge Case 계획 요약표

| 번호 | Edge Case 시나리오 | 간단 내용 | 중요도 | 난이도 |
| :---: | :--- | :--- | :---: | :---: |
| **1** | 무한 자가 수정 루프 방지 | 워커가 계속 틀린 답을 내서 Validator가 무한 반려할 때, `remaining_steps` 등에 의해 시스템이 안전하게 종료(에러/중단)되는지 확인. | **High** 🔴 | Medium 🟡 |
| **2** | Validator의 환각 (파싱 에러) | Validator 노드가 기대하는 JSON 구조 대신 엉뚱한 텍스트를 반환하여 Pydantic 에러가 발생할 때, 시스템 롤백 및 우아한 예외 처리가 되는지 확인. | **High** 🔴 | Medium 🟡 |
| **3** | 유효하지 않은 스레드 ID로 Resume | 클라이언트가 존재하지 않거나 이미 완료된 `thread_id`로 `/api/chat/resume` 요청을 보낼 때 API 단에서 404/400으로 방어하는지 확인. | Medium 🟡 | Low 🟢 |
| **4** | 인터럽트 상태가 아닌데 Resume | 그래프가 `running` 이나 `idle` 상태일 때 악의적으로 `Command(resume=...)`를 주입할 경우 서버가 뻗지 않고 오류를 반환하는지 확인. | **High** 🔴 | High 🔴 |
| **5** | 악의적인 피드백 페이로드 | `feedback` 입력 필드에 프롬프트 인젝션 코드나 수십 MB의 문자열이 들어올 때 길이 제한/무시 처리가 되는지 확인. | Low 🟢 | Low 🟢 |
| **6** | 존재하지 않는 동적 도구 주입 | `active_tools`에 워커에게 허용되지 않은 엉뚱한 도구 이름이 전달되었을 때 크래시 없이 무시하는지 확인. | Medium 🟡 | Low 🟢 |
| **7** | 도구 리스트가 완전히 비워진 경우 | 동적 필터링 결과 바인딩할 도구가 0개가 된 경우, 순수 LLM으로만 동작하다가 에러 없이 정상 종료 노드에 도달하는지 확인. | Medium 🟡 | Medium 🟡 |
| **8** | 극단적으로 짧은 연결 끊김 | LLM 스트리밍 중 사용자가 브라우저 탭을 닫아 파이프(Broken Pipe)가 끊길 때, 그 시점까지의 Trace 데이터가 유실 없이 DB에 저장되는지 확인. | Medium 🟡 | High 🔴 |
