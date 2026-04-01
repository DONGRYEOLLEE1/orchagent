작성일시: 2026-03-31 10:52 KST
최종 수정일시: 2026-03-31 10:52 KST

# Coding Team Instructions & Tool Calling Research Report

## 요약

`coding_team`을 새로 넣으려면 단순히 "코드를 잘 짜는 프롬프트"를 하나 추가하는 방식으로는 부족하다. 상용 coding agent들은 공통적으로 아래 구조를 갖는다.

- 지침은 단일 프롬프트가 아니라 `글로벌 -> 레포/프로젝트 -> 경로/역할 -> 세션/사용자 요청`으로 계층화한다.
- 툴 콜링은 모델 자유 재량에만 맡기지 않고 `allowlist`, `approval mode`, `sandbox`, `environment setup`, `tool namespace`로 제어한다.
- `shell/edit` 같은 로컬 실행 도구와 `MCP` 같은 외부 연동 도구를 같은 층위로 다루지 않는다.
- `plan/read-only` 단계와 `write/run` 단계를 분리하거나, 최소한 승인 모드를 나눈다.
- 세션 중 shell, edit, browser, test, MCP 호출 이력을 사용자에게 드러낸다.

`orchagent`에 적용할 때의 핵심 결론은 이렇다.

- `coding_team`은 `research_team`과 달리 `repo-local coding work`에 집중해야 한다.
- 프롬프트 설계는 반드시 워커 capability와 일치해야 한다.
- V1에서도 `read/search`, `edit`, `exec`, `playwright`, `web/docs`, `MCP`를 별도 권한층으로 나눠야 한다.
- 기존 `TeamBuilder + reviewer` 패턴을 그대로 재사용하되, coding 전용 supervisor policy를 별도로 둬야 한다.

## 조사 범위

- OpenAI Codex
- Anthropic Claude Code
- Cursor
- GitHub Copilot Coding Agent
- Devin

조사 관점은 두 가지였다.

1. coding agent의 지속 지침을 어디에, 어떤 우선순위로 저장하는가
2. tool calling을 어떤 승인/허용/환경 모델로 통제하는가

## 현재 orchagent 기준 수용 지점

현재 코드베이스에서 `coding_team`을 수용하기 좋은 지점은 이미 존재한다.

- `apps/backend/workflow/main_graph.py`
  - 현재 `research_team`, `writing_team`, `vision_team`, `data_science_team`을 `head_supervisor` 아래에 연결한다.
- `packages/agent-core/src/agent_core/builder.py`
  - `TeamBuilder`가 `team supervisor -> workers -> reviewer(optional)` 구조를 공통화한다.
- `apps/backend/workflow/teams/data_science.py`
  - 전용 supervisor prompt와 capability가 다른 워커 둘을 분리한 가장 좋은 참고 사례다.
- `packages/agent-tools/src/agent_tools/file_io.py`
  - 현재는 문서 편집/읽기와 범용 Python REPL 정도만 있고, coding agent가 기대하는 shell/edit/test/git/browser 수준의 도구 계약은 없다.

즉, `coding_team`의 문제는 "팀 추가" 자체보다도 `지침 계층`과 `툴 정책`을 coding 업무에 맞게 새로 정의하는 데 있다.

## 상용 서비스 비교

| 서비스 | 지속 지침 구조 | 툴 제어 구조 | 안전/승인 구조 | orchagent에 주는 시사점 |
| --- | --- | --- | --- | --- |
| OpenAI Codex | `AGENTS.md`, 프로젝트별 `.codex/config.toml`, 프로필, 개발자 지침 | MCP 서버, app tool enable/approval, role별 config | `approval_policy`, `sandbox_mode`, role별 sandbox 상속 | repo 규칙과 역할별 정책을 분리하고, tool approval을 설정값으로 다뤄야 한다 |
| Claude Code | `CLAUDE.md`, `.claude/rules`, auto memory, user/org/project scope | core tool + hooks + MCP 서버 | permission mode, classifier 기반 auto mode, managed MCP | 지침 계층과 tool interception 훅이 중요하다 |
| Cursor | Project Rules, User Rules, Memories, Custom Modes | mode별 tool 조합, MCP tool toggle, background agent env | tool approval 기본 on, auto-run 가능, 격리 원격 머신 | "모드"와 "툴셋"을 함께 설계해야 한다 |
| GitHub Copilot | repo custom instructions, path-specific instructions, `AGENTS.md`, custom agent markdown prompt | `tools:` allowlist, namespaced MCP tools, built-in GitHub/Playwright MCP | repo settings 기반 자율 실행, MCP allowlist 강제 권장 | coding agent는 per-agent tool allowlist가 핵심이다 |
| Devin | knowledge base, playbooks, session history, org knowledge | shell/IDE/browser + MCP marketplace | 격리 VM, 세션 관리, 권한 기반 advanced capabilities | 세션 가시성과 재사용 가능한 playbook 축적이 중요하다 |

## 1. OpenAI Codex

### 지침 패턴

OpenAI Codex는 `AGENTS.md`를 지속 지침의 핵심 단위로 둔다. 공식 가이드는 Codex가 작업 전에 `AGENTS.md`를 읽고, 글로벌 파일과 프로젝트 파일을 계층적으로 적용한다고 설명한다. 또한 글로벌 기본값은 `~/.codex/config.toml`, 프로젝트별 동작은 `.codex/config.toml`에 분리하는 패턴을 권장한다.

핵심 시사점:

- repo 규칙은 코드와 함께 버전관리되는 파일에 둔다.
- 개인 기본값과 프로젝트 규칙은 같은 저장소에 섞지 않는다.
- 역할별 agent를 추가할 때도 config layer와 instruction layer를 분리한다.

### 툴 콜링 패턴

Codex는 `config.toml`에서 `approval_policy`, `sandbox_mode`, MCP 서버, app tool enablement, per-tool approval, agent role config를 분리해서 다룬다. `/permissions`, `/mcp`, `/agent`, `/review` 같은 명시적 조작 surface도 제공한다.

핵심 시사점:

- `coding_team`은 단순 프롬프트가 아니라 별도 tool policy surface가 필요하다.
- `read-only`, `workspace-write`, `full access` 같은 실행 모드는 product-level concept여야 한다.
- sub-agent는 부모 sandbox/approval을 상속해야 일관성이 생긴다.

## 2. Anthropic Claude Code

### 지침 패턴

Claude Code는 `CLAUDE.md`와 auto memory를 분리한다. `CLAUDE.md`는 사용자가 쓰는 규칙이고, auto memory는 Claude가 세션 중 학습한 패턴을 축적하는 층이다. 또한 `project/user/org` scope와 `.claude/rules/` 기반 path-specific rules를 지원한다.

중요한 점은 규칙 파일이 "강제 설정"이 아니라 "context"라는 것이다. Anthropic은 규칙이 길고 모순되면 준수율이 떨어진다고 명시한다.

핵심 시사점:

- `coding_team` 지침은 짧고 검증 가능한 규칙이어야 한다.
- `repo-wide rule`과 `path-specific rule`을 분리하는 구조가 monorepo에 특히 유리하다.
- 이후 `coding_team`을 넣을 때 `orchagent`도 `AGENTS.md + path rule` 호환층을 고려할 가치가 있다.

### 툴 콜링 패턴

Claude Code의 permission mode는 매우 잘게 나뉜다.

- `default`: 민감 작업 전 수동 승인
- `acceptEdits`: 파일 편집은 더 느슨하게 허용
- `plan`: 읽기/탐색/계획만 하고 실제 수정은 하지 않음
- `auto`: classifier가 행동을 검사하며 승인 프롬프트를 줄임
- `dontAsk`: 사전 허용된 도구만 실행
- `bypassPermissions`: 완전 우회

또한 hooks는 `PreToolUse`, `PostToolUse`, `PermissionRequest` 같은 이벤트에서 도구 실행을 가로채고 수정하거나 추가 문맥을 넣을 수 있다. MCP는 별도 trust boundary로 취급되며, 조직 차원 allowlist/denylist와 exclusive managed config까지 지원한다.

핵심 시사점:

- `coding_team`에도 `plan/read-only`와 `edit/run` 모드를 분리하는 편이 낫다.
- tool 호출 전후 hook 지점이 있어야 한다.
- 외부 connector/MCP는 조직 정책으로 잠글 수 있어야 한다.

## 3. Cursor

### 지침 패턴

Cursor는 `Project Rules`, `User Rules`, `Memories`를 분리하고, rules를 `.cursor/rules` 아래에서 관리한다. Rule type도 `Always`, `Auto Attached`, `Agent Requested`로 나뉜다. 또한 `Custom Modes`에서 도구 조합과 instructions를 함께 설정한다.

핵심 시사점:

- 단일 "coding prompt"보다 `always rule`, `path-triggered rule`, `agent-requested skill`의 3층이 실제 운영성이 좋다.
- coding agent는 "누가 이 규칙을 언제 context에 넣는가"가 매우 중요하다.
- `mode = instruction + tools`라는 개념은 `coding_team` 설계에도 그대로 유효하다.

### 툴 콜링 패턴

Cursor 문서 기준으로 Agent는 코드베이스 탐색, 다중 파일 편집, 명령 실행, 에러 수정까지 담당하고, custom mode마다 tool selection을 다르게 가져간다. MCP 도구는 채팅에서 enable/disable 할 수 있고, 기본적으로 approval 후 실행되며 auto-run도 제공한다. Background Agent는 격리된 Ubuntu 머신에서 동작하고 `.cursor/environment.json`으로 설치/시작/terminal 구성을 버전관리할 수 있다.

핵심 시사점:

- `coding_team`은 worker prompt뿐 아니라 `environment contract`가 필요하다.
- Playwright나 dev server 검증은 session/worker가 아니라 환경 설정과 함께 가야 한다.
- 장기적으로는 "interactive coding agent"와 "background coding agent"를 구분하는 편이 낫다.

## 4. GitHub Copilot Coding Agent

### 지침 패턴

GitHub Copilot은 repository custom instructions와 path-specific instructions를 명시적으로 분리한다.

- `.github/copilot-instructions.md`: 레포 전체
- `.github/instructions/*.instructions.md`: 경로 기반
- `AGENTS.md`: AI agent 전용 지침

공식 문서는 path-specific instruction과 repo-wide instruction이 동시에 적용될 수 있고, VS Code 기준으로 가장 가까운 `AGENTS.md`가 precedence를 가진다고 설명한다.

핵심 시사점:

- `coding_team`에는 적어도 `repo-wide coding policy`와 `path-specific coding policy`가 필요하다.
- `AGENTS.md` 호환 전략을 택하면 외부 coding agent와의 상호운용성이 좋아진다.

### 툴 콜링 패턴

GitHub Copilot custom agent는 YAML frontmatter의 `tools:`로 사용 가능한 도구를 명시한다. 여기서 핵심은 "agent별 allowlist"다.

- `tools`를 비우면 모든 툴 차단
- `["read", "edit", "search"]`처럼 alias 단위 허용 가능
- `some-mcp-server/tool-1`처럼 서버 네임스페이스 단위 허용 가능
- 기본 MCP 서버 중 `github/*`, `playwright/*` 같은 패턴을 허용 가능

또한 repository-level MCP 설정에서 GitHub는 "allowlist된 read-only tool만 우선 허용하라"고 강하게 권고한다. 중요한 이유는 coding agent가 이 MCP tool들을 자율적으로 사용할 수 있고, 승인을 다시 묻지 않기 때문이다.

핵심 시사점:

- `coding_team`의 worker마다 tool allowlist를 달리 가져가야 한다.
- MCP는 "서버 추가"보다 "어떤 tool 이름을 노출할지"가 더 중요하다.
- GitHub/Playwright처럼 고빈도 도구는 built-in namespace처럼 다루는 게 UX상 유리하다.

## 5. Devin

### 지침 패턴

Devin은 단순 instruction file 중심이라기보다 `knowledge base`, `playbooks`, `session history`를 통한 재사용성을 강조한다. 특히 advanced capabilities 문서는 성공한 세션을 playbook으로 만들고, 조직 knowledge를 유지하는 흐름을 전면에 둔다.

핵심 시사점:

- `coding_team`이 장기적으로 가치 있으려면 단발성 대화보다 "반복 가능한 작업 절차"를 축적해야 한다.
- 단순 memory보다 `debug playbook`, `release checklist`, `repo-specific failure pattern` 같은 절차형 자산이 중요하다.

### 툴 콜링 패턴

Devin session tools는 shell, IDE, browser 세 축을 명시적으로 사용자에게 노출한다. MCP marketplace는 stdio/SSE/HTTP를 지원하며, 외부 서비스 계정 연결은 service account 사용을 권장한다. 또한 큰 작업을 병렬 session으로 나누는 managed Devin orchestration도 제공한다.

핵심 시사점:

- `coding_team`에는 shell/edit/browser 가시성이 필요하다.
- 조직형 MCP는 개인 계정이 아니라 공유 서비스 계정 기준으로 설계해야 한다.
- 이후 멀티 에이전트 확장 시 "병렬 coding subtask" 모델이 유효하다.

## 공통 설계 패턴

상용 서비스 전반에서 반복되는 패턴은 아래 여섯 가지다.

### 1. 지침은 계층화된다

거의 모든 제품이 아래 구조를 갖는다.

- 개인 글로벌 규칙
- 레포/프로젝트 규칙
- 경로/도메인 규칙
- agent role 전용 규칙
- 세션 또는 현재 user request

단일 system prompt만으로 운영하는 제품은 사실상 없다.

### 2. tool calling은 "허용된 도구 집합" 개념이 먼저다

잘 되는 제품일수록 "무슨 도구가 있나"보다 "이 agent가 어떤 도구를 쓸 수 있나"를 먼저 정의한다.

- worker별 allowlist
- MCP server별 allowlist
- destructive/open-world 분리
- read/search와 edit/exec 분리

### 3. 계획과 실행을 분리한다

Claude의 `plan`, Cursor의 `Ask`, Copilot/Custom Agent의 read/search 전용 조합, Codex의 plan mode는 모두 같은 방향이다.

- 먼저 읽고
- 계획을 만들고
- 그 다음 수정/실행한다

`coding_team`도 처음부터 edit 권한을 항상 들고 있게 하면 프롬프트 품질보다 실수 리스크가 먼저 커진다.

### 4. MCP는 외부 도구가 아니라 별도 trust boundary다

상용 제품들은 MCP를 "도구 하나 더"로 취급하지 않는다.

- 별도 설정
- 별도 인증
- 서버 단위 enable/disable
- 도구 단위 allowlist
- 조직 정책

이 경계가 없으면 prompt injection과 credential misuse 리스크가 급격히 커진다.

### 5. 세션 가시성이 중요하다

Devin의 shell/IDE/browser, Copilot의 agent session/PR trace, Cursor background agent, Codex diff/review/status처럼 사용자는 에이전트가 무엇을 했는지 다시 볼 수 있어야 한다.

### 6. "자동화"는 이진값이 아니라 여러 단계다

수동 승인 vs 완전 자동 둘 중 하나가 아니라, 대부분 제품은 아래 중간층을 둔다.

- read-only
- edit-only
- workspace auto
- external tool prompt
- full bypass

## orchagent용 coding_team 제안

### 1. 팀 경계

`coding_team`은 아래 요청을 담당하는 것이 맞다.

- 레포 내부 코드 수정
- 버그 재현과 디버깅
- 테스트 추가/수정
- 리팩터링
- 빌드/런타임 오류 조사
- 프런트엔드 UI 수정 후 브라우저 검증

반대로 아래는 기본적으로 다른 팀으로 보내는 편이 낫다.

- 최신 외부 정보 조사: `research_team`
- 장문 보고서/문서 산출: `writing_team`
- 이미지 자체 해석: `vision_team`
- 구조적 파일 데이터 분석: `data_science_team`

### 2. V1 워커 구성

V1은 2~3명 구성이 가장 현실적이다.

1. `codebase_explorer`
   - 권한: `read/search` 중심
   - 목적: 관련 파일, 호출 흐름, 설정, 오류 지점 식별

2. `implementation_engineer`
   - 권한: `read/search/edit/exec`
   - 목적: 실제 코드 수정, 로컬 검증, 회귀 보강

3. `ui_verifier` 또는 `runtime_verifier` (선택)
   - 권한: `exec/playwright/browser`
   - 목적: UI/런타임 동작 검증

현재 `orchagent`의 reviewer 루프는 그대로 재사용할 수 있으므로, reviewer는 별도 worker보다 validator로 두는 편이 자연스럽다.

### 3. supervisor 기본 흐름

권장 기본 흐름:

1. `codebase_explorer`
2. `implementation_engineer`
3. `reviewer`
4. 필요 시 `runtime_verifier`
5. `FINISH`

중요한 점은 `explorer`와 `implementation`의 프롬프트를 분리하는 것이다. 현재 research team에서 겪었던 것처럼 capability와 prompt가 어긋나면 routing 품질이 바로 무너진다.

### 4. instruction hierarchy 제안

`coding_team`에는 최소 아래 다섯 층이 필요하다.

1. `SYSTEM_SUPERVISOR_PROMPT`
   - 전체 제품 규칙
2. `CODING_TEAM_SUPERVISOR_PROMPT`
   - 언제 explorer부터 시작할지
   - 언제 runtime/browser 검증을 요구할지
   - 언제 review 후 finish할지
3. worker prompt
   - `CODEBASE_EXPLORER_PROMPT`
   - `IMPLEMENTATION_ENGINEER_PROMPT`
   - `RUNTIME_VERIFIER_PROMPT`
4. repo-local durable instructions
   - `AGENTS.md`, 향후 path-specific rule
5. 현재 user request

### 5. tool calling contract 제안

#### 기본 툴 계층

| 계층 | 도구 예시 | 기본 정책 |
| --- | --- | --- |
| Read/Search | `rg`, file read, symbol 탐색 | 기본 허용 |
| Edit | patch/write/structured edit | workspace 한정 허용 |
| Execute | test, lint, build, dev server | 허용하되 명령 범주 제한 |
| Browser | Playwright, local page inspect | UI 작업 시에만 허용 |
| Web/Docs | 공식 문서 검색, version-sensitive lookup | 필요 시 허용, 일반 web은 제한 |
| Git | `status`, `diff`, `log` | 읽기 명령 기본 허용 |
| Destructive Git | `reset --hard`, force push, branch delete | 기본 금지 또는 승인 필요 |
| External MCP | GitHub/Jira/Sentry/Figma 등 | 서버별, 툴별 allowlist 필요 |

#### V1 정책

- `codebase_explorer`
  - 허용: `read/search`
  - 비허용: `edit`, `exec`, `browser`
- `implementation_engineer`
  - 허용: `read/search/edit`, `test/build/lint`
  - 조건부: `browser`, `web/docs`
- `runtime_verifier`
  - 허용: `exec`, `browser`, `playwright`
  - 비허용: 광범위 코드 수정

### 6. MCP 정책 제안

MCP는 별도 정책으로 다뤄야 한다.

- 기본값은 `off`
- server별 enable
- tool별 allowlist
- read-only 우선
- credential은 서비스 계정 기반
- tool name namespace를 trace에 남김

V1에서 현실적인 MCP 후보:

- `github/*`: issue, PR, code search
- `playwright/*`: UI 검증
- `sentry/*` 또는 `datadog/*`: 운영 디버깅이 필요해질 때

### 7. observability 요구사항

`coding_team`이 실제로 유용하려면 아래 trace가 보여야 한다.

- 어떤 파일을 읽었는지
- 어떤 명령을 실행했는지
- 어떤 파일을 수정했는지
- 어떤 테스트를 돌렸는지
- 어떤 브라우저 검증을 했는지
- 어떤 MCP tool을 호출했는지

현재 `chat_turns`, `trace_events`, `tool_execution_events`, `llm_usage_events` 구조는 이미 있으므로, coding team은 이 축을 그대로 활용하면 된다.

## orchagent에 대한 구체 권고

### 당장 필요한 것

1. `coding_team`을 새 팀으로 추가한다.
2. `prompt-kit`에 coding 전용 supervisor/worker prompt를 분리 정의한다.
3. `worker capability != prompt responsibility` 문제를 피하기 위해 read-only worker와 edit worker를 분리한다.
4. `tool policy`를 프롬프트가 아니라 코드 레벨에서 통제한다.
5. `playwright`와 `web/docs`는 기본 툴이 아니라 조건부 툴로 둔다.

### V1에서 하지 않는 것이 좋은 것

- 범용 unrestricted shell
- repo 외부 네트워크를 항상 허용
- write 권한과 web access를 모든 worker에 동시 부여
- 개인 계정 기반 MCP credential
- planning 없이 곧바로 edit부터 시작하는 default routing

### 추천 구현 순서

1. `codebase_explorer + implementation_engineer + reviewer` 3단 구조
2. `read/search/edit/exec`만 우선 도입
3. Playwright 검증 추가
4. GitHub/Playwright MCP 추가
5. path-specific coding rules와 playbook/memory 확장

## 결론

상용 coding agent들을 비교해 보면, 좋은 제품의 핵심은 "코드를 잘 짜는 모델"이 아니라 아래 세 가지다.

- 계층화된 지침 시스템
- 세밀한 tool allowlist와 approval/sandbox
- 실행 이력의 가시성과 재검증 가능성

따라서 `orchagent`의 `coding_team`도 `연구팀 프롬프트를 조금 바꾼 개발자 버전`처럼 만들면 안 된다. `coding_team`은 별도 팀 정책, 별도 worker capability, 별도 tool contract를 가진 독립 팀으로 설계하는 편이 맞다.

현재 코드베이스 기준으로는 `TeamBuilder`와 existing reviewer loop를 재사용하면서, `data_science_team` 수준의 전용 supervisor policy를 갖는 방향이 가장 자연스럽다.

## 출처

- OpenAI Codex
  - https://developers.openai.com/codex/guides/agents-md/
  - https://developers.openai.com/codex/config-reference/
  - https://developers.openai.com/codex/learn/best-practices/
  - https://developers.openai.com/codex/cli/slash-commands/
  - https://developers.openai.com/codex/multi-agent/
- Anthropic Claude Code
  - https://code.claude.com/docs/en/memory
  - https://code.claude.com/docs/en/permission-modes
  - https://code.claude.com/docs/en/hooks
  - https://code.claude.com/docs/en/mcp
- Cursor
  - https://docs.cursor.com/context/rules
  - https://docs.cursor.com/chat/custom-modes
  - https://docs.cursor.com/advanced/model-context-protocol
  - https://docs.cursor.com/en/background-agents
  - https://docs.cursor.com/agent/tools
- GitHub Copilot
  - https://docs.github.com/en/copilot/reference/custom-agents-configuration
  - https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions
  - https://docs.github.com/copilot/using-github-copilot/coding-agent/extending-copilot-coding-agent-with-mcp
- Devin
  - https://docs.devin.ai/work-with-devin/advanced-capabilities
  - https://docs.devin.ai/work-with-devin/devin-session-tools
  - https://docs.devin.ai/work-with-devin/mcp
