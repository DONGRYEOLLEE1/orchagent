작성일시: 2026-03-26 09:59 KST

# Long-Term Memory Personalization Research Report

## 요약

주요 상용 AI 에이전트 서비스들은 장기 기억을 거의 비슷한 구조로 구축한다.

- `명시적 메모리`: 사용자가 직접 저장하거나 설정에서 편집하는 선호도, 역할, 스타일, 도메인 정보
- `추론 메모리`: 과거 대화나 검색 기록에서 시스템이 추출한 요약/인사이트
- `조회 계층`: 요약 메모리와 과거 대화 검색(RAG)을 함께 사용
- `스코프 분리`: 전역 계정 메모리와 프로젝트/조직/특정 공간 메모리를 분리
- `제어 장치`: temporary/incognito chat, on/off 토글, 개별 삭제, 전체 초기화, 관리자 제어

공개 문서상 각 서비스의 실제 물리 스키마는 대부분 비공개다. 따라서 아래 분석은 2026-03-26 기준 공식 도움말/제품 공지에 기반한 `확인된 사실`과, 그 사실로부터 도출한 `설계 해석`을 분리해 정리한다.

## OrchAgent 코드베이스 빠른 파악

현재 `orchagent`는 장기 기억을 직접 구현하지는 않았지만, 메모리 시스템을 꽂기 좋은 뼈대는 이미 갖고 있다.

- 런타임 그래프는 `planner -> head_supervisor -> teams -> finalizer` 구조이며 `apps/backend/workflow/main_graph.py`에서 조립된다.
- 그래프 상태에는 merge 가능한 `shared_context`와 `artifacts`가 있으며 `packages/agent-core/src/agent_core/state.py`가 이를 정의한다.
- `/api/chat`는 현재 사용자 입력과 `force_requires_approval`만 `shared_context`에 넣어 그래프를 시작한다. 즉, 개인화 컨텍스트를 넣을 1차 주입 지점은 이미 있다.
- supervisor는 `packages/agent-core/src/agent_core/supervisor.py`에서 시스템 프롬프트와 `task_plan`만 합성한다. 아직 memory block은 없다.
- 모든 시스템 프롬프트는 `packages/prompt-kit/src/prompt_kit/prompts.py`에 모여 있어, 메모리 관련 프롬프트 정책도 이 패키지에 추가해야 한다.
- 데이터 계층에는 `auth_users`, `chat_sessions`, `chat_messages`, `thread_profiles`, `chat_turns`, `llm_usage_events`, `tool_execution_events`, `trace_events`가 이미 있다.
- 프런트엔드에는 `AccountDrawer`와 `ProfilePanel`이 있어 메모리 설정 UI를 붙일 자리가 있다.

현재 부족한 것은 다음 네 가지다.

- 사용자/스레드 수준의 canonical memory 저장소
- turn 시작 전에 memory를 회수해 `shared_context`에 넣는 retrieval 계층
- turn 종료 후 메모리를 갱신하는 write-back 계층
- 사용자가 memory를 보고, 수정하고, 끌 수 있는 API/UI

중요한 점은 `thread_profiles`는 title/pinned/archive 같은 UI 메타데이터용이며, 장기 기억 저장소로 재사용하면 의미가 섞인다는 것이다.

## 조사 범위

조사 대상은 메모리/개인화 기능을 공식적으로 공개한 상용 AI 서비스다.

- OpenAI ChatGPT
- Google Gemini Apps
- Anthropic Claude
- Microsoft 365 Copilot
- Perplexity

## 서비스별 조사

## 1. OpenAI ChatGPT

### 확인된 사실

- OpenAI는 2025-04-10 업데이트에서 ChatGPT memory가 두 방식으로 동작한다고 설명했다.
  - `saved memories`: 사용자가 기억하라고 한 정보
  - `chat history`: 과거 대화에서 수집한 인사이트
- 사용자는 `saved memories`와 `chat history`를 각각 끌 수 있고, 대화 중 직접 기억을 수정/삭제하게 할 수 있다.
- `Temporary Chat`는 history에 남지 않고 memory를 사용하거나 갱신하지 않으며, 모델 학습에도 사용하지 않는다.
- `Custom Instructions`는 여전히 별도 개인화 채널로 유지된다.
- Team/Enterprise에서는 조직 차원의 memory 제어가 가능하다.

### 설계 해석

OpenAI의 공개 동작만 봐도 memory를 최소 3계층으로 분리해 운용한다고 해석하는 것이 타당하다.

- `명시적 메모리 저장소`
- `과거 대화 기반 inferred memory`
- `대화별 우회 모드(Temporary Chat)`

즉, 단순히 “과거 대화 몇 개를 더 context에 붙인다”가 아니라 `저장형 profile memory`와 `history-derived memory`를 분리하고, 정책적으로 독립 토글을 둔 구조다.

### OrchAgent 시사점

- `user_profile`과 `memory`를 같은 개념으로 합치지 말고 분리해야 한다.
- `temporary chat` 같은 bypass 모드가 없으면 메모리 오염과 프라이버시 리스크가 커진다.
- 명시적 기억과 inferred 기억을 한 테이블에 섞더라도 `source_type`은 분리해야 한다.

출처:

- [OpenAI: Memory and new controls for ChatGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/)

## 2. Google Gemini Apps

### 확인된 사실

- Gemini Apps 도움말은 personalization을 두 기능으로 설명한다.
  - `memory of your past chats`
  - `instructions`
- personalization 기능은 개인 Google 계정 로그인 상태에서만 제공되며, work/school/supervised account에서는 제한된다.
- temporary chat에서는 personalized responses를 제공하지 않고, future personalization을 위한 정보 저장도 하지 않는다.
- signed-out 상태에서는 past chats 접근과 personalized responses가 불가능하다.

### 설계 해석

Gemini는 memory를 “과거 채팅 기억”으로, instructions를 “명시적 사용자 설정”으로 분리한다. 또한 personalization 자체를 `계정 상태`와 `activity retention`에 강하게 종속시킨다.

이는 다음 구조를 시사한다.

- 계정 레벨 personalization store
- past-chat retrieval 또는 summary layer
- explicit instruction profile
- temporary/anonymous path에서는 memory read/write 차단

### OrchAgent 시사점

- 현재 `orchagent`도 인증 기반 서비스이므로 memory는 `authenticated user`에만 제공하는 방향이 자연스럽다.
- 익명/임시/민감 세션에서 memory를 끄는 `request-level flag`가 필요하다.
- explicit instructions panel은 memory panel과 분리하는 편이 운영상 명확하다.

출처:

- [Gemini Apps Help: Get personalization in Gemini Apps](https://support.google.com/gemini/answer/16598623?hl=en)
- [Gemini Apps Help: Use Gemini Apps](https://support.google.com/gemini/answer/13275745?hl=en)

## 3. Anthropic Claude

### 확인된 사실

- Anthropic은 2025-09-11에 Claude memory를 발표했고, 2025-10-23에 Pro/Max까지 확장했다고 공지했다.
- Claude Help Center는 과거 채팅 검색이 `RAG`로 동작하며 대화 중 tool call로 보인다고 설명한다.
- Claude는 chat history를 요약한 `memory summary`를 생성하며, 이 synthesis는 24시간마다 갱신된다.
- project마다 별도 memory space와 project summary가 존재한다.
- memory summary는 사용자가 직접 보고 수정할 수 있다.
- past chat을 참조할 때 원본 chat citation을 제공한다.
- incognito chat은 memory에 저장되지 않으며 검색 대상에도 포함되지 않는다.
- Enterprise owner는 조직 차원에서 memory를 끄면 전체 memory synthesis를 삭제할 수 있다.

### 설계 해석

Claude는 공개된 서비스 중 memory 구조를 가장 선명하게 드러낸다.

- `summary memory`
  - 독립 실행형 새 대화에 기본으로 주입되는 요약 레이어
- `retrieval memory`
  - 필요 시 과거 채팅을 검색하는 RAG 레이어
- `scoped namespace`
  - global chat memory와 project memory를 분리
- `visibility/control`
  - memory summary를 사용자가 직접 보고 수정
- `citation/debuggability`
  - 어떤 과거 대화를 참조했는지 사용자에게 노출

### OrchAgent 시사점

- 단순 key-value memory보다 `summary + retrieval` 하이브리드가 실전성이 높다.
- 현재 `orchagent`에는 project 개념이 없으므로 1차 스코프는 `user_global`과 `thread_local`로 시작하는 편이 맞다.
- memory가 실제로 어떤 turn에 주입됐는지 `reference log`를 남기지 않으면 디버깅이 어렵다.

출처:

- [Anthropic Blog: Bringing memory to Claude](https://claude.com/blog/memory)
- [Claude Help Center: Use Claude’s chat search and memory to build on previous context](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context)

## 4. Microsoft 365 Copilot

### 확인된 사실

- Microsoft는 2026-02 기준 Copilot personalization을 세 축으로 설명한다.
  - `Saving memories to Copilot Memory`
  - `Making inferences from chat history`
  - `Using custom instructions`
- Temporary Chat는 personalized information을 읽거나 저장하지 않으며 chat history에도 남지 않는다.
- Copilot Memory는 중요해 보이는 정보를 자동 제안하거나, 사용자가 “remember”라고 직접 저장할 수 있다.
- saved memories는 설정에서 관리할 수 있고, Copilot은 관련 memory를 병합/갱신/삭제해 관리한다.
- Microsoft는 Copilot Memory가 communication style, favorite topics, work goals, recurring tasks 같은 정보를 기억한다고 설명한다.

### 설계 해석

Copilot도 사실상 OpenAI와 유사한 삼중 구조다.

- explicit saved memories
- chat history inference
- custom instructions

여기에 `memory hygiene`가 더 강조된다. 즉, memory를 append-only로 쌓는 것이 아니라 병합/업데이트/정리하는 `maintenance layer`가 존재한다는 뜻이다.

### OrchAgent 시사점

- 메모리 시스템은 `create-only`보다 `merge/update/archive`가 중요하다.
- 반복적으로 같은 선호가 들어오면 새 row를 계속 추가하지 말고 기존 memory를 승격/병합하는 정책이 필요하다.
- custom instructions는 memory와 별도 edit surface로 두는 편이 좋다.

출처:

- [Microsoft Support: Get started with personalizing what Microsoft 365 Copilot remembers](https://support.microsoft.com/en-us/topic/get-started-with-personalizing-what-microsoft-365-copilot-remembers-cba7b79a-c46f-4ca7-b46e-2fa22c563f90)
- [Microsoft Support: Manage Copilot Memory in Microsoft 365 Copilot](https://support.microsoft.com/en-us/topic/manage-copilot-memory-in-microsoft-365-copilot-b3231eae-9e60-4b3c-ac58-81fddbe56279)
- [Microsoft Support: Customize how Microsoft 365 Copilot responds to you](https://support.microsoft.com/en-us/topic/customize-how-microsoft-365-copilot-responds-to-you-frontier-8b826c0d-eb78-493e-a30d-4490ec1c4b9e)
- [Microsoft Support: Revisit your Microsoft 365 Copilot Chat history](https://support.microsoft.com/en-us/topic/search-your-microsoft-365-copilot-chat-history-2f015346-9d04-450c-8b1c-a895cd0733cd)

## 5. Perplexity

### 확인된 사실

- Perplexity는 memory를 `Memories`와 `Search history`의 두 경로로 설명한다.
- 시스템은 질문에 따라 memory와 previous searches 중 어느 소스를 쓸지 자동으로 결정한다.
- Perplexity는 답변에 memory/history reference를 source로 표시한다.
- memory는 preferences, interests, information이 축적되는 `dynamic and evolving memory bank`라고 설명한다.
- 사용자는 memory와 search history를 각각 독립적으로 켜고 끌 수 있다.
- incognito mode에서는 memory와 previous searches가 항상 꺼져 있다.
- 삭제된 memory는 최대 30일 동안 안전/디버깅/즉시 재생성 방지 목적의 로그로 남을 수 있다.
- enterprise memory 문서는 조직 관리자 제어, 데이터 소유권, 암호화, category view, 시크릿 모드 예외를 설명한다.
- 다만 2026-03-26 기준 공식 문서 사이에 불일치가 있다.
  - 일반 Memory 문서는 "enterprises and organizations에는 아직 제공되지 않는다"라고 적는다.
  - 별도 Enterprise Memory 문서는 실제 enterprise용 memory 동작과 관리자 제어를 설명한다.
  - 따라서 enterprise 동작은 staged rollout 또는 help-center 반영 시차가 있는 상태로 해석하는 편이 안전하다.

### 설계 해석

Perplexity는 memory를 “검색 개인화”에 더 가깝게 운용하지만, 구조는 매우 유용하다.

- `saved memory`
- `search-history recall`
- `automatic source selection`
- `response-level provenance`
- `incognito bypass`
- `enterprise governance`

즉, 기억을 저장하는 것만큼 `이 답변이 어떤 기억을 참조했는지`를 표면화하는 UX가 중요하다는 점을 보여준다.

### OrchAgent 시사점

- `memory_reference_events` 같은 정규화 테이블이 있으면 나중에 UI에서 “이 답변은 어떤 기억을 참고했는지”를 보여주기 쉽다.
- memory toggle과 history toggle은 분리하는 편이 좋다.
- 삭제 후 재생성 방지 로그나 tombstone 개념이 없으면 inferred memory가 반복 생성될 수 있다.

출처:

- [Perplexity Help Center: Memory](https://www.perplexity.ai/help-center/en/articles/10968016-memory)
- [Perplexity Help Center: Memory for Enterprise Organizations](https://www.perplexity.ai/help-center/ko/articles/13654357-%EA%B8%B0%EC%97%85-%EC%A1%B0%EC%A7%81%EC%9D%84-%EC%9C%84%ED%95%9C-%EB%A9%94%EB%AA%A8%EB%A6%AC)

## 비교 요약

| 서비스 | 저장 경로 | 조회 경로 | 스코프 | 제어 장치 |
| --- | --- | --- | --- | --- |
| ChatGPT | saved memories + chat history insights | 미래 대화에 memory/history 반영 | 계정 전역, 조직 제어 | memory/history 개별 토글, temporary chat |
| Gemini | past chats + instructions | personalized responses | 개인 계정 전역 | sign-in gating, temporary chat |
| Claude | memory summary + chat-search RAG | summary 기본 주입 + RAG tool call | 전역, project 분리 | pause/reset, incognito, citation, admin control |
| Microsoft 365 Copilot | saved memories + chat history inference + custom instructions | personalization context 주입 | 조직 계정 전역 | temporary chat, saved memory 관리, custom instructions |
| Perplexity | memories + search history | 자동 source selection + citation | 개인/조직, incognito 제외 | memory/history 분리 토글, category 관리, admin control |

## 반복되는 설계 패턴

### 1. explicit memory와 inferred memory를 분리한다

가장 공통적인 패턴이다. 사용자가 직접 적어준 profile/instruction과, 과거 대화에서 시스템이 추론한 기억은 lifecycle과 신뢰도가 다르다.

### 2. summary memory와 retrieval memory를 같이 쓴다

Claude가 가장 명시적이지만, 다른 서비스도 사실상 같은 방향이다.

- 요약 메모리는 매 turn마다 싸게 넣기 좋다.
- retrieval 메모리는 필요할 때만 정밀하게 끌어오기 좋다.

### 3. scope를 분리한다

전역 계정 memory만 있으면 문맥 오염이 쉽게 생긴다. project, workspace, organization, incognito 같은 namespace가 반복적으로 등장한다.

### 4. temporary/incognito path를 반드시 둔다

상용 제품 대부분이 장기 기억 read/write를 우회하는 대화 모드를 따로 둔다.

### 5. 사용자가 memory를 볼 수 있어야 한다

단순 토글만으로는 부족하다. 상용 제품은 대체로 memory list나 summary를 보여주고, 개별 삭제나 전체 초기화를 지원한다.

### 6. memory hygiene가 중요하다

Copilot의 merge/update/remove, Claude의 daily synthesis, Perplexity의 dynamic memory bank처럼, 메모리는 append-only log가 아니라 정리되는 상태여야 한다.

### 7. provenance가 있으면 디버깅이 쉬워진다

Claude의 citation, Perplexity의 source 표기처럼 memory reference를 추적 가능하게 만들면 personalization 디버깅과 사용자 신뢰가 좋아진다.

## OrchAgent에 대한 적용 해석

현재 코드베이스를 기준으로 보면 `orchagent`는 다음 방향이 가장 현실적이다.

### 바로 활용 가능한 기반

- `auth_users`와 `chat_sessions.user_id`가 있어 user ownership이 이미 있다.
- `shared_context` merge 구조가 있어 memory retrieval 결과를 graph 전역에 주입하기 쉽다.
- prompt가 `prompt-kit`로 중앙화되어 있어 memory 정책을 한 곳에서 관리할 수 있다.
- `trace_events`, `chat_turns`, `llm_usage_events`가 있어 memory reference observability를 붙이기 좋다.
- `AccountDrawer`가 있어 memory 관리 UI 진입점이 이미 있다.

### 아직 없는 것

- `memory entry` canonical table
- `memory settings` table
- `memory retrieval` service
- `memory extraction` service
- `memory reference` logging
- `temporary chat / memory off` request flag

### 권장 도입 전략

리스크와 구현 난이도를 함께 보면 `explicit memory -> retrieval integration -> inferred memory` 순서가 가장 안전하다.

1. `explicit memory`부터 시작한다.
   - 언어, 답변 포맷, 톤, 기술 스택, 자주 다루는 도메인 같은 저위험 선호만 저장
2. read path를 붙여 `shared_context.personalization`에 memory를 주입한다.
3. prompt-kit에서 supervisor/finalizer/worker가 memory를 참고하는 규칙을 추가한다.
4. 사용자가 memory를 보고 수정/삭제할 수 있게 한다.
5. 그 다음에만 자동 inferred memory extraction을 켠다.

## 최종 결론

상용 서비스들은 장기 기억을 “대화 히스토리를 더 길게 붙이는 기능”으로 취급하지 않는다. 실제로는 아래 조합으로 운영한다.

- 명시적 profile/instruction memory
- 과거 대화 기반 inferred memory
- summary + retrieval의 하이브리드 read path
- scope namespace
- temporary/incognito bypass
- 사용자/관리자 제어
- reference visibility와 maintenance policy

`orchagent`는 이미 인증, thread, trace, prompt, shared state 구조가 갖춰져 있으므로 메모리 시스템을 무리 없이 붙일 수 있다. 다만 처음부터 자동 inferred memory까지 한 번에 넣기보다, `explicit memory + retrieval + control surface`를 먼저 안정화한 뒤 자동 추출을 확장하는 것이 가장 현실적이다.
