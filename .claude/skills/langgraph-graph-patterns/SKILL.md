---
name: langgraph-graph-patterns
description: "OrchAgent의 LangGraph 계층형 그래프를 설계·수정할 때 반드시 따라야 하는 규약과 관용 패턴. StateGraph 스키마, supervisor/validator 노드, create_agent 기반 워커, interrupt/Command HITL, PostgresSaver 체크포인터, 서브그래프 persistence, Send API 팬아웃, prompt-kit 단일 관리 원칙을 포함한다. `packages/agent-core`, `apps/backend/workflow` 수정 시 또는 LangGraph state/노드/엣지 설계 시 반드시 이 스킬을 읽는다."
---

# LangGraph Graph Patterns — OrchAgent 설계 규약

OrchAgent의 LangGraph 그래프를 수정·확장할 때 지켜야 할 핵심 규약과 관용 패턴.

## AGENTS.md 강제 규칙 (위반 시 리팩토링 대상)

| 규칙 | 이유 |
|------|------|
| LLM은 `langchain.chat_models.init_chat_model`로만 초기화 | 모델 교체/테스트 목킹이 단일 지점 |
| 워커 에이전트는 `langchain.agents.create_agent`로만 구성 | 미들웨어/툴/프롬프트 결합이 공식 경로 |
| `langgraph.prebuilt.create_react_agent` 절대 사용 금지 | 프레임워크 내부 구조 노출 시 업그레이드 리스크 |
| 모든 프롬프트는 `packages/prompt-kit`에서만 정의·import | 프롬프트 감사/리뷰가 한 곳에서 |

참조 위치:
- LLM 초기화: `apps/backend/workflow/main_graph.py`
- 워커 생성: `packages/agent-core/src/agent_core/builder.py`
- 프롬프트: `packages/prompt-kit/src/prompt_kit/prompts.py`

## 그래프 구조 (Head → Team → Worker)

```
Head Supervisor (라우팅 결정 + HITL interrupt 지점)
├── Research Supervisor ── [Tavily / Web Scraper / ... ] → Research Validator → (self-correct)
├── Writing Supervisor  ── [Doc Writer / Note Taker / Chart Generator] → Writing Validator
├── Vision Supervisor   ── [Vision Analyst + metadata/resize tools] → Vision Validator
├── Coding Supervisor   ── [Coding workers + coding tools]
└── Finalizer (최종 응답 synthesizer, FINAL_RESPONSE_STREAM_OWNERSHIP 계약 준수)
```

팀 단위는 독립 서브그래프. 최상위 체크포인터(PostgresSaver) 아래 서브그래프는 `subgraphs=True`로 persistence 상속.

## 상태 스키마 원칙 (`agent_core/state.py`)

- **최소화** — 필드는 라우팅·검증·SSE emit에 실제 필요한 것만. 툴 실행 중간 산출물은 체크포인터가 알아서 보존
- **Reducer 명시** — 리스트/딕트 병합은 `add_messages`, `operator.add` 등 명시. 암묵적 교체 의존 금지
- **Optional vs Default** — 신규 필드는 `Optional[X] = None`로 시작. 기본값이 의미 있을 때만 default 설정
- **Subgraph 필드 분리** — 팀 내부에서만 쓰는 state는 최상위 state에 올리지 않음. 필요 시 team-local state + 최상위로 넘길 output state 분리

**state 변경은 breaking change**. 영향 범위를 열거하고 마이그레이션 순서 제안 후 구현.

## Supervisor 패턴 (`agent_core/supervisor.py`)

- supervisor는 **라우팅만** 결정. 실제 작업은 워커 서브그래프/노드가 수행
- 반환: `Command(goto="team-name", update={...})` 또는 `Command(goto="finalizer")` 또는 `Command(goto="__end__")`
- LLM에게 라우팅 이유를 `reasoning` 필드로 반환받아 SSE `reasoning`/`route` 이벤트로 emit
- Head supervisor는 `interrupt()`를 통해 인간 승인을 받을 수 있는 지점 포함 가능

## Validator 패턴 (`agent_core/validator.py`)

- 워커 출력 품질을 검사 → 통과면 `FINISH`, 실패면 재시도 요청을 state에 기록하고 supervisor로 복귀
- **무한 루프 방지**: state에 `retry_count` 필드, 상한(2~3회) 도달 시 강제 통과 + 경고 기록
- 실패 사유를 구체적으로 state에 남겨 다음 워커 실행이 이를 활용 가능하게

## Worker 생성 (`agent_core/builder.py`)

```python
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from prompt_kit.prompts import RESEARCH_WORKER_PROMPT
from agent_tools.web import tavily_search_tool, scrape_tool

llm = init_chat_model("openai:gpt-4.1", temperature=0)
worker = create_agent(
    llm=llm,
    tools=[tavily_search_tool, scrape_tool],
    prompt=RESEARCH_WORKER_PROMPT,
)
```

- 툴은 `packages/agent-tools`에서, 프롬프트는 `packages/prompt-kit`에서 import
- 워커를 서브그래프 노드로 감쌀 때 state adapter로 입출력 매핑

## HITL (interrupt + Command.resume)

- **interrupt 위치**: Head supervisor의 승인 단계, 위험 툴(코드 실행, 파일 쓰기) 실행 전
- interrupt 시 state에 `pending_approval` 같은 필드로 이유·옵션 기록 → API가 그대로 프론트에 노출
- `Command(resume={"approved": True, "feedback": "..."})`으로 복귀
- resume 경로는 기존 `thread_id`로 그래프 재실행. 새 thread 만들지 않음

## 체크포인터 (PostgresSaver)

- 최상위 그래프: `PostgresSaver.from_conn_string(...)` 후 `graph.compile(checkpointer=saver)`
- 서브그래프: 명시적 checkpointer 지정 없이 컴파일하고 부모에서 `subgraphs=True` 활성화 → 부모 체크포인터 상속
- `thread_id`는 API가 세션/대화 단위로 관리. URL routing과 일치(`CHAT_THREAD_URL_ROUTING_PLAN` 참조)

## Send API (팬아웃)

- 한 supervisor가 여러 워커를 병렬 실행 시 `Send("worker-name", worker_state)` 리스트 반환
- 결과는 reducer로 병합 — reducer 없이 팬아웃하면 state overwrite 발생 위험

## SSE emit 지점 매핑

| LangGraph 상태 변화 | SSE 이벤트 |
|-------------------|-----------|
| supervisor 라우팅 결정 | `route` |
| supervisor/worker가 reasoning 텍스트 생성 | `reasoning` |
| 툴 호출 시작/종료 | `tool` |
| 워커가 텍스트 청크 스트림 | `text` |
| 체크포인트 저장 | `checkpoint` |
| interrupt 발생 | `status: pending_approval` |

상세 shape은 `sse-contract` 스킬 참조.

## 설계 검토 체크리스트

- [ ] state 변경이 breaking이면 영향 범위 목록 있나?
- [ ] `create_react_agent` 사용 없나?
- [ ] 프롬프트 하드코딩 없나?
- [ ] `retry_count` 등 루프 방지 카운터 있나?
- [ ] interrupt 위치가 예측 가능한가? (워커 내부 interrupt 없어야)
- [ ] 서브그래프 persistence 모드 명시됐나?
- [ ] SSE emit 지점과 state 변화가 매핑됐나?
- [ ] 영향 받는 테스트 파일 목록(`test_workflow_graph.py`, `test_supervisor.py`, `test_validator_edge_cases.py` 등) 업데이트 계획 있나?

## 관련 참조

- `langchain-fundamentals`, `langgraph-fundamentals`, `langgraph-persistence`, `langgraph-human-in-the-loop`, `langchain-middleware` 스킬(글로벌)에서 표준 패턴 재확인 가능
- `docs/FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT.md` — 최종 응답 스트림 계약
- `docs/HIERARCHICAL_MODERNIZATION_PLAN.md` 등 관련 plans
