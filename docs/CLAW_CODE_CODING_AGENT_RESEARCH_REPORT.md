작성일시: 2026-04-01 17:58 KST
최종 수정일시: 2026-04-01 17:58 KST

# Claw-Code Rust Runtime Research For OrchAgent Coding Agent

## 요약

`~/workspace/claw-code`의 `Analysis.md`와 Rust 런타임 코드를 기준으로 보면, claw-code의 강점은 단순히 "도구가 많다"가 아니다. 진짜 강점은 아래 네 가지다.

- 모델 스트림, 툴 호출, 세션 저장, 권한 판정, 훅 실행이 분리된 중간 런타임 계층
- 도구별 `PermissionMode`와 샌드박스 상태를 갖는 명시적 실행 정책
- `ToolUse / ToolResult`를 대화 세션의 1급 블록으로 취급하는 상태 모델
- MCP, hooks, config layering, instruction discovery가 모두 런타임 구조 안에 들어와 있다는 점

현재 `orchagent`는 이미 `repo binding -> turn workspace -> coding_team -> trace/tool log -> final response`까지 도달했다. 즉, "repo를 서버 workspace에서 수정하는 웹 기반 coding agent"의 최소 골격은 생겼다.

하지만 claw-code와 비교하면 아직 아래가 부족하다.

- 권한 모델이 툴별/모드별로 정식 객체화되어 있지 않다.
- pre/post tool hook 계층이 없다.
- tool output이 structured diff/patch 중심이 아니라 상대적으로 느슨하다.
- 장기 실행 command/background task/session resume 모델이 약하다.
- MCP를 server/tool namespace 단위로 정책화하는 계층이 없다.

따라서 `orchagent`의 다음 단계는 "도구를 몇 개 더 붙이는 것"이 아니라, `coding runtime control plane`을 강화하는 방향이 맞다.

## 조사 범위

- `~/workspace/claw-code/Analysis.md`
- `~/workspace/claw-code/rust/crates/runtime/*`
- `~/workspace/claw-code/rust/crates/tools/src/lib.rs`
- `~/workspace/claw-code/rust/crates/rusty-claude-cli/*`
- 현재 `orchagent`의 coding 관련 구현
  - `apps/backend/workflow/teams/coding.py`
  - `apps/backend/services/repository_binding_service.py`
  - `packages/agent-tools/src/agent_tools/coding.py`
  - `apps/frontend/src/components/workspace/RepositoryBindingPanel.tsx`

## claw-code Rust 런타임에서 중요한 점

## 1. 툴 호출은 "모델이 직접 실행"이 아니라 "이벤트 -> 런타임 -> 실행" 구조다

`Analysis.md`와 Rust 코드 기준으로 claw-code는 다음 흐름을 갖는다.

1. 모델 스트림 수신
2. 스트림을 `AssistantEvent`로 정규화
3. `ToolUse` 블록을 런타임이 해석
4. 권한 정책 검사
5. pre-tool hook
6. 실제 tool 실행
7. post-tool hook
8. `ToolResult`를 세션에 저장

이 구조는 `orchagent`에도 그대로 중요하다. 웹 기반 제품일수록 "실행"보다 "실행 직전과 직후를 통제하는 중간 계층"이 더 중요하기 때문이다.

근거:

- `Analysis.md`
- `rust/crates/runtime/src/conversation.rs`
- `rust/crates/rusty-claude-cli/src/main.rs`

### OrchAgent 시사점

- 현재 `orchagent`도 LangGraph + tool execution trace는 있지만, pre/post execution decision layer는 약하다.
- `coding_team`은 다음 단계에서 "툴 실행 전 정책 엔진"과 "툴 실행 후 결과 정규화 계층"을 가져야 한다.

## 2. 권한은 tool별 mode로 모델링된다

claw-code는 `PermissionMode`를 명시적으로 둔다.

- `ReadOnly`
- `WorkspaceWrite`
- `DangerFullAccess`
- `Prompt`
- `Allow`

그리고 각 tool은 필요한 최소 permission을 선언한다. 대표적으로:

- `read_file`, `glob_search`, `grep_search`는 `ReadOnly`
- `write_file`, `edit_file`, `TodoWrite`는 `WorkspaceWrite`
- `bash`, `Agent`는 `DangerFullAccess`

근거:

- `rust/crates/tools/src/lib.rs`
- `rust/crates/runtime/src/permissions.rs`

### OrchAgent 시사점

현재 `orchagent`는 coding tools를 `worker allowlist` 수준으로 나누긴 했지만, 아직 `tool permission model`이 정식 구조로 존재하지 않는다.

다음 단계에서는 최소한 아래 permission tier를 도입하는 것이 좋다.

- `read_only`
- `workspace_write`
- `workspace_execute`
- `browser_verify`
- `external_mcp`
- `dangerous`

핵심은 worker에 도구를 붙이는 것과 별개로, 도구 자체가 permission tier를 갖게 해야 한다는 점이다.

## 3. 샌드박스는 "상태"로 계산되고 결과에 남는다

claw-code는 샌드박스가 단순 설정이 아니라 `SandboxStatus`로 계산된다.

- namespace isolation active 여부
- network isolation active 여부
- filesystem mode
- allowed mounts
- fallback reason

즉, "샌드박스를 켰다"가 아니라 "이번 실행에서 실제로 어떤 격리가 살아 있었는가"를 남긴다.

근거:

- `rust/crates/runtime/src/sandbox.rs`

### OrchAgent 시사점

현재 `orchagent`도 workspace root 제한은 있지만, 실행 결과에 "이번 command가 어떤 권한/격리 상태에서 돌았는가"가 충분히 명시되지는 않는다.

web 제품에서는 이 정보가 더 중요하다.

- 관리자/운영자가 audit 해야 함
- 사용자에게도 어느 수준까지 실행했는지 보여줄 수 있어야 함
- trace/debug에서 policy mismatch를 찾아야 함

즉, `tool_execution_events`와 final response metadata에 아래를 남기는 게 좋다.

- permission_mode
- workspace_root
- network_enabled
- repo_binding_id
- workspace_job_id
- fallback_reason

## 4. hooks가 정식 런타임 계층이다

claw-code는 `PreToolUse`, `PostToolUse` hook를 표준 계층으로 둔다.

- pre-hook는 실행 차단 가능
- post-hook는 결과에 메시지 추가 가능
- 실패해도 기본 실행은 계속될 수 있음

근거:

- `rust/crates/runtime/src/hooks.rs`

### OrchAgent 시사점

현재 `orchagent`의 coding agent에 가장 부족한 부분 중 하나가 hook 계층이다.

이건 특히 웹 기반 멀티에이전트 제품에서 중요하다.

권장 hook:

- `pre_command_policy_hook`
  - `rm -rf`, `curl | sh`, broad glob delete 차단
- `post_command_summary_hook`
  - stdout/stderr를 더 짧게 정리
- `pre_patch_guard_hook`
  - workspace root 밖 edit 차단, huge file edit 차단
- `post_patch_diff_hook`
  - structured diff와 changed file list 생성
- `pre_mcp_policy_hook`
  - server/tool allowlist 확인

## 5. 세션 상태가 툴 블록을 1급 시민으로 갖는다

claw-code의 `Session`은 단순 텍스트 메시지 배열이 아니다.

- `Text`
- `ToolUse`
- `ToolResult`

를 같은 메시지 블록 체계 안에 넣는다.

근거:

- `rust/crates/runtime/src/session.rs`

### OrchAgent 시사점

현재 `orchagent`는 `chat_messages`와 `trace_events/tool_execution_events`가 분리돼 있어서 운영 관점에선 좋지만, coding turn을 replay하거나 model-visible state를 재구성할 때는 중간 구조가 다소 흩어져 있다.

즉, 다음 단계에서는 최소한 internal runtime state에 아래를 구조화하는 편이 좋다.

- `tool_calls[]`
- `tool_results[]`
- `structured_patch[]`
- `verification_runs[]`

DB 스키마를 전면 갈아엎을 필요는 없지만, `shared_context`나 `artifacts` 쪽에 "model이 다음 단계에서 읽기 좋은 구조화 결과"가 있어야 한다.

## 6. config와 instruction discovery가 runtime 안에 있다

claw-code는 `RuntimeConfig`가 `user/project/local` 설정을 병합하고, `prompt.rs`가 `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/instructions.md` 같은 instruction 파일을 상향식으로 발견한다.

근거:

- `rust/crates/runtime/src/config.rs`
- `rust/crates/runtime/src/prompt.rs`

### OrchAgent 시사점

`orchagent`도 결국 웹 기반 coding agent라면, repo 자체가 가진 coding policy를 읽어야 한다.

권장 우선순위:

1. `AGENTS.md`
2. `CLAUDE.md`
3. repo-local `.claude/*` / `.cursor/rules/*`
4. OrchAgent server-side policy
5. current user request

즉, `repo binding` 후 materialize 시점에 instruction discovery를 한 번 수행하고, 그 결과를 `coding_team` system context에 넣는 것이 좋다.

## 현재 OrchAgent의 위치

현재 구현 기준으로 `orchagent`는 이미 아래를 갖는다.

### 이미 있는 것

- thread 단위 repo binding
  - URL / zip / registered repo
- turn 단위 server-side workspace
  - `repo/`, `artifacts/`, `logs/`
- coding team
  - `codebase_explorer`
  - `implementation_engineer`
  - `runtime_verifier`
- 최소 coding tools
  - tree/search/read
  - patch/create
  - allowlisted command run
  - git read
  - local page verify
- UI repo ingress
  - URL bind
  - zip bind
  - bound repo card
- Playwright 검증 완료
  - local git URL repo bug fix
  - zip ingress repo bug fix

### 아직 약한 것

- tool permission tier가 정식 모델이 아님
- pre/post tool hook 부재
- structured patch/diff output이 비교적 느슨함
- command가 foreground 일회성 중심
- MCP policy layer 부재
- repo-local instruction discovery 부재
- symbolic/code-intelligence 계층 부재

## OrchAgent에 권장하는 고도화 방향

## 1. coding runtime control plane을 추가한다

지금은 `tool function -> trace` 구조가 중심인데, 다음 단계에선 아래 레이어가 필요하다.

- tool request normalization
- permission evaluation
- hook execution
- tool execution
- structured result shaping
- artifact registration
- state append

즉, `coding_team`을 더 잘 만들려면 worker 프롬프트보다 runtime middle layer를 먼저 강화하는 게 맞다.

## 2. tool 반환값을 더 구조화한다

claw-code의 `write_file/edit_file`은 단순 success string이 아니라 아래를 가진다.

- original_file
- structured_patch
- git_diff
- user_modified

`orchagent`도 coding tool은 가능한 한 아래 형태를 표준화하는 게 좋다.

| tool | 최소 반환 필드 |
| --- | --- |
| `read_repo_file` | `file_path`, `start_line`, `end_line`, `content_excerpt` |
| `apply_patch_edit` | `file_path`, `changed`, `patch_preview`, `old_hash`, `new_hash` |
| `run_repo_command` | `command`, `exit_code`, `stdout_excerpt`, `stderr_excerpt`, `log_file` |
| `git_diff` | `changed_files`, `diff_excerpt`, `artifact_log` |

이렇게 해야 reviewer와 finalizer가 후속 reasoning을 안정적으로 할 수 있다.

## 3. permission mode를 OrchAgent 고유 개념으로 올린다

권장 mode:

| mode | 의미 |
| --- | --- |
| `read_only` | file read/search only |
| `workspace_write` | patch/create allowed |
| `workspace_execute` | test/build/lint/dev server allowed |
| `browser_verify` | local page / Playwright verify allowed |
| `external_mcp` | GitHub/Sentry/Jira 등 외부 tool allowed |
| `dangerous` | destructive git/system ops |

그리고 tool은 각자 required mode를 가진다.

이렇게 되면

- UI에서 현재 turn permission을 설명할 수 있고
- 운영 정책을 바꾸기 쉽고
- hook과 reviewer 판단도 명확해진다.

## 4. repo-local instruction discovery를 넣는다

권장 구현:

- workspace hydrate 직후 아래 파일 탐색
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.claude/CLAUDE.md`
  - `.claude/instructions.md`
  - `.cursor/rules/*`
- 발견 내용을 길이 제한 후 `shared_context.repo_instructions`에 적재
- `coding_team` system prompt에 별도 섹션으로 합성

이건 web 제품에서도 중요하다. 사용자는 "왜 agent가 이 스타일로 수정했는가"를 repo 규칙으로 설명받을 수 있어야 한다.

## 5. background execution model을 추가한다

claw-code의 현재 background 모델도 강하진 않지만, 최소한 foreground 일회성만 있는 것보다는 낫다.

`orchagent`는 웹 제품이므로 background job 모델이 훨씬 중요하다.

권장 작업:

- `run_repo_command`에 background mode 추가
- workspace job과 별도로 `background_processes` 상태 추적
- UI에서 long-running test/build/dev server 상태 표시
- 이어지는 `runtime_verifier`가 이전 process를 reuse 가능하게 설계

특히 frontend repo나 e2e-heavy repo는 이게 없으면 실사용성이 낮다.

## 6. MCP를 namespace 정책으로 도입한다

claw-code는 MCP tool 이름을 server prefix와 함께 정규화한다.

`orchagent`도 MCP는 단순 tool 추가가 아니라 아래 기준으로 넣는 게 좋다.

- server name
- tool name
- allowed worker
- permission mode
- service account

즉, 이런 식이 좋다.

| namespace | 용도 |
| --- | --- |
| `github/*` | repo, issue, PR, code search |
| `playwright/*` | 브라우저 검증 |
| `sentry/*` | 운영 에러 조사 |
| `linear/*` | 작업 티켓 참조 |

## OrchAgent coding agent tool 세분화 제안

아래는 `orchagent`에 넣는 것이 좋은 fine-grained tool taxonomy다.

## A. Repo Ingress / Binding

| tool | 목적 | permission |
| --- | --- | --- |
| `bind_repo_url` | git/GitHub URL binding | `read_only` |
| `bind_repo_zip` | zip repo binding | `workspace_write` |
| `unbind_repo` | current binding 제거 | `workspace_write` |
| `refresh_repo_binding` | cache restage / fetch | `workspace_execute` |
| `inspect_repo_binding` | 현재 thread repo 정보 조회 | `read_only` |

## B. Workspace Lifecycle

| tool | 목적 | permission |
| --- | --- | --- |
| `create_workspace_snapshot` | turn용 repo workspace 생성 | internal |
| `finalize_workspace_job` | turn 종료 시 상태 마감 | internal |
| `list_workspace_artifacts` | artifacts/logs 조회 | `read_only` |
| `cleanup_workspace` | TTL/삭제 | internal |

## C. Code Understanding

| tool | 목적 | permission |
| --- | --- | --- |
| `list_repo_tree` | 디렉토리 구조 보기 | `read_only` |
| `search_repo_text` | 문자열/rg 검색 | `read_only` |
| `read_repo_file` | 파일 읽기 | `read_only` |
| `summarize_repo_file` | 파일 책임 요약 | `read_only` |
| `find_tests_for_target` | 관련 테스트 위치 찾기 | `read_only` |

## D. Symbol / Semantic Navigation

이건 현재 `orchagent`에 아직 없지만, 다음 단계 우선순위가 높다.

| tool | 목적 | permission |
| --- | --- | --- |
| `find_symbol` | 함수/타입 정의 찾기 | `read_only` |
| `find_references` | 심볼 사용처 찾기 | `read_only` |
| `find_callers` | 호출자 탐색 | `read_only` |
| `find_implementations` | trait/interface 구현 탐색 | `read_only` |
| `dependency_slice` | 수정 영향 범위 요약 | `read_only` |

이 계층이 있어야 `codebase_explorer`가 grep-only worker를 넘어서게 된다.

## E. Safe Edit

| tool | 목적 | permission |
| --- | --- | --- |
| `apply_patch_edit` | exact snippet patch | `workspace_write` |
| `create_repo_file` | 새 파일 생성 | `workspace_write` |
| `replace_symbol_block` | 함수/블록 단위 교체 | `workspace_write` |
| `insert_after_anchor` | 특정 anchor 뒤 삽입 | `workspace_write` |
| `delete_block` | 안전한 블록 삭제 | `workspace_write` |

## F. Structured Diff / Review Support

| tool | 목적 | permission |
| --- | --- | --- |
| `git_status` | 변경 파일 목록 | `read_only` |
| `git_diff` | patch 확인 | `read_only` |
| `git_diff_for_file` | 파일 단위 diff | `read_only` |
| `summarize_patch` | diff 요약 | `read_only` |

## G. Verification / Command Execution

| tool | 목적 | permission |
| --- | --- | --- |
| `run_repo_command` | allowlisted command 실행 | `workspace_execute` |
| `run_tests_targeted` | 관련 테스트만 실행 | `workspace_execute` |
| `run_lint_targeted` | 관련 lint 실행 | `workspace_execute` |
| `run_build_targeted` | 빌드/타입체크 | `workspace_execute` |
| `start_dev_server` | local dev server 시작 | `workspace_execute` |
| `stop_background_process` | long-running process 종료 | `workspace_execute` |
| `tail_process_logs` | background process 로그 확인 | `read_only` |

## H. Browser / Runtime Verification

| tool | 목적 | permission |
| --- | --- | --- |
| `verify_local_page` | localhost text/assert 확인 | `browser_verify` |
| `playwright_open_page` | local page 열기 | `browser_verify` |
| `playwright_assert_text` | UI 텍스트 검증 | `browser_verify` |
| `playwright_assert_visibility` | 버튼/컴포넌트 가시성 검증 | `browser_verify` |
| `playwright_take_screenshot` | 증빙 이미지 생성 | `browser_verify` |

## I. Docs / Dependency Intelligence

| tool | 목적 | permission |
| --- | --- | --- |
| `fetch_official_docs` | 최신 공식 문서 확인 | `read_only` |
| `inspect_package_manifest` | package.json/Cargo.toml/pyproject 분석 | `read_only` |
| `resolve_dependency_version` | 실제 버전 확인 | `read_only` |
| `find_cli_scripts` | build/test script 추출 | `read_only` |

## J. Observability / Incident

| tool | 목적 | permission |
| --- | --- | --- |
| `inspect_runtime_logs` | server/app logs 확인 | `read_only` |
| `inspect_test_artifacts` | junit/coverage/snapshot 확인 | `read_only` |
| `inspect_error_trace` | stack trace 요약 | `read_only` |
| `fetch_recent_failures` | 마지막 실패 이력 조회 | `read_only` |

## K. Task / Workflow

| tool | 목적 | permission |
| --- | --- | --- |
| `todo_write` | coding task breakdown | `workspace_write` |
| `mark_verification_status` | 검증 상태 마킹 | internal |
| `handoff_summary` | worker 간 전달 요약 | internal |

## L. MCP Integration

| tool namespace | 목적 | permission |
| --- | --- | --- |
| `github/*` | issue/PR/code search | `external_mcp` |
| `playwright/*` | 브라우저 MCP 검증 | `browser_verify` |
| `sentry/*` | 운영 에러 조회 | `external_mcp` |
| `linear/*` | 작업 티켓 참조 | `external_mcp` |

## 우선순위 제안

## V1 다음 단계

- `PermissionMode` 정식 도입
- pre/post tool hook
- repo-local instruction discovery
- structured patch/diff payload 강화

## V2

- symbol/reference 계층
- background process model
- MCP namespace policy
- richer browser verification

## V3

- 병렬 coding subtasks
- repo-wide semantic index
- patch risk scoring
- automated rollback / retry lanes

## 결론

claw-code의 핵심 교훈은 "강한 coding agent는 bash가 센 agent"가 아니라는 점이다.  
강한 coding agent는 다음이 강하다.

- tool permission model
- tool lifecycle hooks
- structured tool result state
- layered repo instructions
- session/replay/audit model

`orchagent`는 이미 웹 제품 기준으로 가장 어려운 첫 단계를 넘겼다.

- repo ingress
- server-side isolated workspace
- coding_team
- final response with artifacts

이제 진짜 고도화 포인트는 `tool 수`보다 `runtime policy와 state richness`다.  
즉, 다음 단계는 `coding runtime control plane`을 강화하는 쪽이 맞다.

## 참고 파일

claw-code:

- [Analysis.md](/Users/drlee/workspace/claw-code/Analysis.md)
- [tools/src/lib.rs](/Users/drlee/workspace/claw-code/rust/crates/tools/src/lib.rs)
- [runtime/src/conversation.rs](/Users/drlee/workspace/claw-code/rust/crates/runtime/src/conversation.rs)
- [runtime/src/permissions.rs](/Users/drlee/workspace/claw-code/rust/crates/runtime/src/permissions.rs)
- [runtime/src/sandbox.rs](/Users/drlee/workspace/claw-code/rust/crates/runtime/src/sandbox.rs)
- [runtime/src/hooks.rs](/Users/drlee/workspace/claw-code/rust/crates/runtime/src/hooks.rs)
- [runtime/src/session.rs](/Users/drlee/workspace/claw-code/rust/crates/runtime/src/session.rs)
- [runtime/src/config.rs](/Users/drlee/workspace/claw-code/rust/crates/runtime/src/config.rs)
- [runtime/src/prompt.rs](/Users/drlee/workspace/claw-code/rust/crates/runtime/src/prompt.rs)

orchagent 현재 구현:

- [coding.py](/Users/drlee/workspace/orchagent/apps/backend/workflow/teams/coding.py)
- [repository_binding_service.py](/Users/drlee/workspace/orchagent/apps/backend/services/repository_binding_service.py)
- [coding.py](/Users/drlee/workspace/orchagent/packages/agent-tools/src/agent_tools/coding.py)
- [RepositoryBindingPanel.tsx](/Users/drlee/workspace/orchagent/apps/frontend/src/components/workspace/RepositoryBindingPanel.tsx)
