# Phase 1-1: 네이티브 서브그래프 통합 계획 (Native Subgraph Integration)

## 1. 목표 (Objective)
현재의 동기식 `.invoke()` 서브그래프 호출 방식을 LangGraph의 네이티브 서브그래프(Native Subgraph) 구조로 마이그레이션합니다. 이를 통해 **토큰 단위 실시간 스트리밍(TTFT 개선)**을 가능하게 하고, 팀 경계를 넘나드는 상태(State) 전파와 체크포인팅을 완벽하게 지원하는 것이 목표입니다.

## 2. 현행 구조와 문제점
*   **현재 방식:** `apps/backend/workflow/main_graph.py`에서 각 팀을 호출할 때 래퍼 함수(`call_research_team` 등)를 사용하여 `team_graph.invoke(state)`를 동기적으로 실행합니다.
*   **문제점:** `invoke()`는 서브그래프의 모든 작업이 끝날 때까지 상위 그래프의 실행을 차단(Blocking)합니다. 따라서 하위 노드에서 발생하는 `on_chat_model_stream` 이벤트가 상위로 전파되지 않아 사용자는 전체 답변이 완성될 때까지 기다려야 합니다.

## 3. 구현 단계 (Implementation Steps)

*   **[x] 단계 1: `main_graph.py` 래퍼 함수 제거 및 직접 연결**
    *   기존의 `call_research_team`, `call_paper_writing_team` 등의 래퍼 함수를 제거합니다.
    *   컴파일된 서브그래프(`research_graph` 등)를 `main_graph`의 노드로 직접 추가합니다. (예: `builder.add_node("research_team", research_graph)`)

*   **[x] 단계 2: 서브그래프 종료 후 라우팅(Edge) 설정**
    *   네이티브 서브그래프로 추가될 경우, 서브그래프의 실행이 끝나면(`END` 도달 시) 상위 그래프의 다음 노드로 이동해야 합니다.
    *   `main_graph`에서 서브그래프 노드 실행 완료 후 다시 `head_supervisor`로 돌아가도록 명시적인 엣지(Edge)를 설정합니다. (예: `builder.add_edge("research_team", "head_supervisor")`)

*   **[ ] 단계 3: 상태(State) 호환성 검증**
    *   상위 그래프와 하위 그래프가 동일한 `BaseAgentState`를 공유하는지 확인합니다.
    *   서브그래프 내부에서 추가된 메시지가 상위 그래프의 메시지 목록에 올바르게 병합(Merge)되는지 점검합니다.

*   **[ ] 단계 4: 스트리밍 및 라우팅 테스트**
    *   수정된 코드를 바탕으로 도커 환경을 재빌드합니다.
    *   UI에서 이스라엘/이란 관련 질문 등 Research Team을 호출하는 질의를 던지고, `astream_events`를 통해 실시간 토큰 스트리밍이 작동하는지 확인합니다.
    *   작업 완료 후 "Coordinating Team" 로딩 바가 정상적으로 사라지는지 점검합니다.

## 4. 기대 효과
*   **TTFT(Time To First Token) 극적 단축:** 에이전트가 생각하는 즉시 화면에 답변이 스트리밍됩니다.
*   **완벽한 Time-Travel:** LangGraph의 체크포인터가 서브그래프 내부의 상태까지 모두 기록하여 디버깅 및 상태 복원이 용이해집니다.
