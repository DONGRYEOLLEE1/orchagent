# TRAJECTORY-CENTERED CONTEXT ENGINEERING FOR ORCHAGENT

작성일: 2026-03-16

## 목적

OrchAgent의 기존 강점인 `trace`, `checkpoint`, `validator`, `route_history`를 활용해, 에이전트가 남긴 trajectory를 다음 실행의 더 좋은 context로 재가공하는 방향을 정리한다. 목표는 다음과 같다.

- 실패/성공 궤적을 재사용 가능한 context 자산으로 전환한다.
- 같은 실수를 반복하지 않도록 reflection과 memory를 붙인다.
- 무작정 전체 대화/전체 trace를 다시 넣지 않고, 다음 step에 필요한 정보만 선택적으로 주입한다.
- 모델 weight update 없이도 test-time 성능을 올릴 수 있는 운영형 개선안을 만든다.

## 왜 지금 OrchAgent에 잘 맞는가

이 레포는 이미 trajectory 기반 개선에 필요한 재료를 상당 부분 갖고 있다.

- 백엔드는 `status`, `route`, `reasoning`, `tool`, `checkpoint` 이벤트를 SSE로 정규화해 보낸다.
- 상태 스키마에 `route_history`, `shared_context`, `artifacts`, `active_tools` 슬롯이 있다.
- validator가 실패 피드백을 자연어로 남긴다.
- checkpointer와 trace 저장 계층이 이미 존재한다.

즉, 지금 필요한 것은 “더 많은 프롬프트”가 아니라 “실행 중 생성된 흔적을 어떤 단위로 추출, 압축, 검색, 재주입할지”에 대한 context engineering 레이어다.

## 조사 결론 요약

현 레포에 가장 잘 맞는 기법은 아래 6가지다.

| 우선순위 | 기법 | 핵심 아이디어 | OrchAgent 적용 방식 |
| :-- | :-- | :-- | :-- |
| P0 | Structured Trajectory Canonicalization | trajectory를 thought/action/observation/feedback 단위로 고정 스키마화 | trace 이벤트를 재사용 가능한 `trajectory artifact`로 변환 |
| P0 | Reflection Memory | 실패 원인과 다음 시도 전략을 자연어 메모리로 축적 | validator 실패, user feedback, tool error 뒤에 reflection 생성 |
| P1 | Dynamic Cheatsheet / Evolving Playbook | 전체 transcript 대신 짧고 전이 가능한 전략만 누적 | 팀별 운영 playbook을 system context 앞단에 주입 |
| P1 | Experience Retrieval | 유사한 과거 실행의 성공/실패 패턴을 검색해 few-shot context로 삽입 | task signature + tool signature 기반 retrieve |
| P1 | Skill Library / Strategy Cards | 반복적으로 유효한 tool-use 패턴을 재사용 가능한 스킬로 분리 | research/writing/vision 전용 카드 라이브러리 생성 |
| P2 | Incremental Refinement Context | 전체 재시도 대신 “무엇을 고칠지”만 주는 refinement context 사용 | validator feedback을 delta brief로 바꿔 retry |

## 기법별 정리

### 1. Structured Trajectory Canonicalization

관련 근거:

- ReAct: reasoning과 action을 교차시켜 trajectory를 명시적으로 남기는 방식이 해석 가능성과 성능을 함께 높였음.
- Generative Agents: 경험을 memory stream으로 쌓고, reflection과 retrieval로 다시 행동 계획에 사용함.

OrchAgent 적용 포인트:

- 현재 SSE 이벤트를 그대로 저장하는 수준에서 한 단계 더 나아가, 실행 종료 시 `trajectory summary`를 별도 산출물로 만든다.
- 추천 최소 스키마:

```json
{
  "task_signature": {
    "intent": "research|writing|vision|mixed",
    "has_image": false,
    "requires_tools": true
  },
  "execution_signature": {
    "teams": ["research"],
    "workers": ["search", "web_scraper"],
    "tools": ["tavily_tool", "scrape_webpages"]
  },
  "outcome": {
    "status": "success|partial|failed|interrupted",
    "final_answer_quality": "unknown|validated|rejected",
    "validator_feedback": ["..."],
    "user_feedback": ["..."]
  },
  "lessons": {
    "worked": ["..."],
    "failed": ["..."],
    "reusable_snippets": ["..."]
  }
}
```

어디에 붙일지:

- `apps/backend/api/routes/chat.py` 종료 시점
- `services/trace_service.py` 또는 별도 `trajectory_service.py`

효과:

- 전체 trace를 다시 넣지 않고도 다음 시도에 필요한 핵심만 골라 쓸 수 있다.
- 이후 reflection, retrieval, skill library의 공통 원본이 된다.

### 2. Reflection Memory

관련 근거:

- Reflexion은 task feedback을 바탕으로 reflective text를 episodic memory buffer에 저장하고 다음 시도에 활용했다.
- Self-Refine는 생성물에 대해 feedback을 만들고 이를 기반으로 iterative refinement를 수행했다.

OrchAgent 적용 포인트:

- reflection 생성 트리거:
  - validator가 `[Validation Failed]`를 남겼을 때
  - tool error가 발생했을 때
  - 사용자가 `reject` 또는 `feedback`으로 재개했을 때
  - interrupted 후 재개 이전/이후
- reflection 포맷 예시:

```text
[Reflection]
Task type: research
What failed: search results were recent but not sufficiently grounded
Why it failed: answer synthesis happened before enough source coverage
Next-time strategy:
1. Use search first for breadth
2. Scrape top 2 authoritative URLs
3. Quote or cite source URLs explicitly
Avoid:
- Answering from model memory when freshness is required
```

어디에 붙일지:

- `packages/agent-core/src/agent_core/validator.py` 이후
- `chat.py`의 `GraphInterrupt`, `tool_error`, `resume` 처리 이후

효과:

- 현재 validator feedback은 “그 순간의 correction”에 머무르는데, reflection memory를 붙이면 “다음번 유사 작업의 prior”가 된다.

### 3. Dynamic Cheatsheet / Evolving Playbook

관련 근거:

- Dynamic Cheatsheet는 긴 transcript 대신 짧고 transferable한 cheatsheet를 누적해 test-time 성능을 올렸다.
- ACE는 evolving playbook을 generation, reflection, curation 순서로 업데이트해 brevity bias와 context collapse를 줄였다.

OrchAgent 적용 포인트:

- `research`, `writing`, `vision`, `head_supervisor`별로 별도 playbook 문서를 둔다.
- playbook은 전체 trajectory 요약이 아니라 아래처럼 “재사용 가능한 운영 규칙”만 저장한다.

예시:

```text
[Research Playbook]
- Freshness-sensitive 질문은 내부 지식으로 답하지 말고 먼저 search를 수행한다.
- search 결과가 약하면 scrape를 추가하고 최종 답변에는 URL을 남긴다.
- validator가 '근거 부족'을 지적한 경우, 재시도 때는 summary보다 source coverage를 먼저 늘린다.
```

운영 원칙:

- append-only가 아니라 curator 단계가 필요하다.
- 같은 규칙의 중복 버전이 생기면 merge한다.
- rule마다 provenance를 붙인다.
  - source_thread_id
  - last_verified_at
  - win_count / fail_count

어디에 붙일지:

- `packages/prompt-kit` 앞단에 runtime-injected context로 주입
- 장기적으로는 `prompt-kit` 정적 prompt와 `playbook` 동적 prompt를 분리

효과:

- 프롬프트가 길어지는 대신 살아있는 운영 지식이 쌓인다.
- 모델이 “최근 이 시스템에서 통하던 방식”을 바로 이어받는다.

### 4. Experience Retrieval

관련 근거:

- ExpeL은 model parameter를 건드리지 않고 agent experience에서 학습하는 방향을 제시했다.
- Voyager는 skill description embedding으로 유사 상황에서 적절한 skill을 재호출했다.

OrchAgent 적용 포인트:

- 새 요청이 들어오면 아래 signature를 만든다.
  - task intent
  - image 포함 여부
  - 예상 팀
  - 도구 조합
  - 실패 유형
- 이 signature로 최근 trajectory summary와 reflection memory를 검색해 top-k를 가져온다.

검색 단위 예시:

- `research + latest info + tavily + scrape`
- `writing + outline -> doc_writer`
- `vision + image metadata insufficient`
- `resume + reject + dangerous operation`

주입 위치:

- head supervisor 앞단: 어떤 팀으로 보내야 하는지
- team supervisor 앞단: 어떤 worker/tool sequence가 잘 먹혔는지
- worker 앞단: 실제 execution hints

효과:

- 같은 task family에서 TTFT 대비 성공률 개선 가능성이 높다.
- 전체 trace 재주입보다 token cost가 낮다.

### 5. Skill Library / Strategy Cards

관련 근거:

- Voyager는 ever-growing skill library로 복잡한 행동을 재사용 가능한 단위로 축적했다.

OrchAgent 적용 포인트:

- 이 레포에서는 실행 가능한 code skill만이 아니라 “tool-use strategy card”가 더 현실적이다.
- 예시 카드:

```text
Title: Latest-news research
When to use:
- user asks for recent facts, rankings, market/news updates
Steps:
1. Search breadth-first
2. Scrape 1-2 authority pages
3. Synthesize only after source coverage check
Avoid:
- answering from memory
```

카드 종류:

- supervisor routing card
- worker execution card
- validator correction card
- HITL escalation card

효과:

- `active_tools`가 아직 약하게만 연결된 현재 구조에서, tool policy를 자연어 카드로 먼저 운영해볼 수 있다.
- 나중에 `active_tools` gating과 결합하기 쉽다.

### 6. Incremental Refinement Context

관련 근거:

- Self-Refine의 핵심은 “전체 생성물을 다시 만들기”보다 “구체적 피드백을 반영해 다음 출력을 개선하는 루프”다.

OrchAgent 적용 포인트:

- 현재는 validator 실패 시 supervisor로 feedback 메시지가 돌아가는데, 다음 단계에서는 이 피드백을 `delta brief`로 정리해준다.
- 예시:

```text
[Delta Brief]
Do not rewrite from scratch.
Keep:
- source selection
- current structure
Fix:
- add explicit source URLs
- distinguish inferred claims from cited facts
```

효과:

- retry token 비용을 줄이고, 성공한 부분을 보존할 수 있다.
- writing/research 계열에서 특히 효과가 클 가능성이 높다.

## OrchAgent 기준 추천 우선순위

### Phase 1. Trajectory Assetization

먼저 할 일:

1. trace 이벤트를 `trajectory summary`로 변환하는 배치 로직 추가
2. validator failure / tool error / user feedback 기반 reflection 생성
3. 팀별 playbook 파일 또는 DB 테이블 신설

이 단계에서 필요한 새 컴포넌트:

- `services/trajectory_service.py`
- `models/trajectory.py` 또는 JSONB 테이블
- `services/reflection_service.py`

### Phase 2. Retrieval Injection

다음 단계:

1. 요청 진입 시 task signature 생성
2. top-k trajectory / reflection / strategy card 검색
3. head supervisor 또는 team supervisor prompt 앞단에 주입

추천 삽입 순서:

1. head supervisor
2. research team
3. writing team
4. vision team

이유:

- supervisor 단계의 context selection이 전체 비용 대비 효과가 가장 크다.

### Phase 3. Policy-Driven Tool Context

이후:

1. strategy card와 `active_tools`를 연결
2. retrieval 결과에 따라 허용 도구 집합을 좁힘
3. validator 결과를 다음번 tool policy에 반영

이 단계가 되면 `active_tools`가 단순 설계 포인트를 넘어 실제 runtime policy로 동작할 수 있다.

## 바로 적용 가능한 최소 실험안

가장 먼저 해볼 만한 A/B 실험은 아래 조합이다.

### 실험 A. Reflection Memory Only

- baseline: 현재 구조
- variant: validator failure 후 3~5줄 reflection을 저장하고, 다음 유사 task에서 supervisor 앞단에 1개만 주입

측정:

- first-pass success rate
- retry success rate
- validator failure recurrence
- average token usage

### 실험 B. Research Playbook Injection

- baseline: 현재 research prompt
- variant: 최근 성공 trajectory에서 추출한 `research playbook` 상위 3개 규칙 주입

측정:

- freshness-sensitive 질문 정답률
- source citation 포함률
- hallucination/unsupported-claim 비율

### 실험 C. Delta Brief Retry

- baseline: validator failure 후 일반 재시도
- variant: validator feedback을 delta brief로 변환해 재시도

측정:

- retry token cost
- retry latency
- second-attempt quality

## 설계 원칙

trajectory 기반 context engineering을 붙일 때는 아래 원칙을 지키는 편이 좋다.

1. 전체 transcript를 계속 누적하지 말 것
2. “이벤트 로그”와 “재사용할 전략”을 분리할 것
3. reflection은 짧고 전이 가능하게 만들 것
4. retrieval 대상에는 반드시 provenance를 남길 것
5. success memory뿐 아니라 failure memory도 관리할 것
6. memory update는 append-only가 아니라 curation 단계를 둘 것

## 추천 데이터 모델

```json
{
  "memory_id": "uuid",
  "memory_type": "reflection|trajectory_summary|strategy_card|playbook_rule",
  "scope": "head|research|writing|vision|global",
  "task_signature": {},
  "source_thread_id": "thread_x",
  "source_run_ids": [],
  "content": "transferable lesson",
  "evidence": {
    "status": "success|failure|partial",
    "validator_feedback": [],
    "user_feedback": []
  },
  "stats": {
    "retrieved_count": 0,
    "accepted_count": 0,
    "last_used_at": null
  }
}
```

## 최종 제안

현 레포에서 가장 현실적인 시작점은 아래 순서다.

1. `trajectory summary` 생성
2. `reflection memory` 생성
3. 팀별 `playbook` 주입
4. signature 기반 retrieval
5. `active_tools`와 strategy card 연결

이 순서는 현재 코드베이스의 강점과 잘 맞는다. 이미 trace, validator, checkpoint, state schema가 있으므로, 거대한 아키텍처 변경 없이도 “실행 흔적을 다음 실행의 context로 바꾸는 루프”를 추가할 수 있다.

## 참고 자료

- ReAct: Synergizing Reasoning and Acting in Language Models
  https://arxiv.org/abs/2210.03629
- Reflexion: Language Agents with Verbal Reinforcement Learning
  https://arxiv.org/abs/2303.11366
- Self-Refine: Iterative Refinement with Self-Feedback
  https://arxiv.org/abs/2303.17651
- Generative Agents: Interactive Simulacra of Human Behavior
  https://arxiv.org/abs/2304.03442
- Voyager: An Open-Ended Embodied Agent with Large Language Models
  https://arxiv.org/abs/2305.16291
- ExpeL: LLM Agents Are Experiential Learners
  https://arxiv.org/abs/2308.10144
- Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory
  https://arxiv.org/abs/2504.07952
- Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  https://arxiv.org/abs/2504.19413
- Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models
  https://arxiv.org/abs/2510.04618
