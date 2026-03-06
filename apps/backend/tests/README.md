# 🧪 OrchAgent Backend Test Suite

이 디렉토리는 OrchAgent 백엔드의 핵심 컴포넌트를 계층별로 검증하기 위한 테스트 스크립트 모음입니다.
`pytest`와 `unittest.mock`을 활용한 **Test Double (Mock, Stub, Monkeypatch)** 기법을 사용하여, 외부 API(OpenAI 등)나 실제 DB 연결 없이도 빠르고 안정적으로 CI 환경에서 실행할 수 있도록 구성되어 있습니다.

## 📝 테스트 스크립트 설명

### 1. 코어 아키텍처 테스트 (Core 5)
- **`test_api.py`** (API 계층)
  - *설명*: FastAPI의 Health Check와 `POST /api/chat`의 SSE 스트리밍 통신이 정상적으로 이루어지는지 검증합니다.
  - *기법*: LangGraph 엔진과 Checkpointer를 `Monkeypatch`로 덮어씌워 가짜(Stub) 이벤트를 반환하게 하여 스트리밍 기능만 순수하게 테스트합니다.
- **`test_trace_service.py`** (데이터베이스/서비스 계층)
  - *설명*: 이벤트를 영구 저장하는 서비스 로직이 정확한 스키마와 파라미터로 호출되는지 검증합니다.
  - *기법*: `AsyncMock`을 활용해 비동기 SQLAlchemy 세션을 Mocking하고, `add()` 및 `commit()` 호출 여부를 확인합니다.
- **`test_agent_tools.py`** (도구/유틸리티 계층)
  - *설명*: 에이전트의 팔다리가 되는 외부 연동 도구(File I/O 등)의 입출력을 검증합니다.
  - *기법*: `pytest`의 `tmp_path` fixture를 활용해 안전한 격리 파일 시스템에서 File IO 도구를 테스트합니다.
- **`test_supervisor.py`** (라우팅/지능 계층)
  - *설명*: LLM이 포함된 Supervisor가 올바른 `Command(goto=...)`를 반환하여 분기 처리를 제대로 하는지 검증합니다.
  - *기법*: 실제 LLM 대신 항상 고정된 값을 리턴하는 `FakeLLM` 클래스(Stub)를 주입하여 프롬프트 파싱 및 Command 생성을 테스트합니다.
- **`test_workflow_graph.py`** (통합 오케스트레이션 계층)
  - *설명*: 복잡한 계층형 LangGraph(Head -> Teams -> Workers)가 구조적 결함(무한루프, 데드락) 없이 성공적으로 컴파일되는지 검증합니다.
  - *기법*: 노드와 엣지의 그래프 스키마 유효성을 LLM 실행 없이(빌드 타임 검증) 확인합니다.

### 2. 고도화 및 안정성 테스트 (Next Steps 3)
- **`test_schemas.py`** (데이터 검증)
  - *설명*: Pydantic을 활용한 API 입력값(ChatRequest)의 유효성 검사 및 에러 반환을 테스트합니다.
- **`test_error_handling.py`** (에러 복구/Fallback)
  - *설명*: 그래프 실행 중 LLM 타임아웃이나 예기치 못한 크래시가 발생했을 때, 클라이언트에게 적절한 에러 이벤트(`{"event": "error"}`)를 스트리밍하는지 방어 로직을 검증합니다.
  - *기법*: Graph 실행부에서 의도적으로 `Exception`을 발생(Raise)시키도록 Mocking합니다.
- **`test_integration_llm.py`** (E2E 연동)
  - *설명*: (선택적 실행) 실제 OpenAI API 키가 존재할 때만 실행되어, 프롬프트나 최신 LLM API 변경에 따른 런타임 연동 문제를 확인합니다.

## 🚀 실행 방법
```bash
cd apps/backend
uv run pytest tests/ -v
```
