---
작업명: Coding Team Repo Workspace Plan
간단요약: 웹 프로덕션 환경에서 동작 가능한 `coding_team`을 위해 GitHub/zip 기반 repo ingress, thread 단위 repo binding, turn 단위 격리 workspace, 최소한의 coding tool contract, 엄격한 검증 흐름을 단계적으로 도입한다.
작성일시: 2026-03-31 17:47 KST
최종 수정일시: 2026-03-31 17:47 KST
---

# Coding Team Repo Workspace Plan

## 배경

`docs/CODING_TEAM_INSTRUCTIONS_TOOL_CALLING_RESEARCH_REPORT.md`를 바탕으로 현재 코드베이스와 실제 웹 UI를 다시 확인해보면, `coding_team`은 "로컬 파일을 읽고 쓰는 도구 몇 개를 추가"하는 수준으로 설계하면 안 된다.

현재 `orchagent`는 웹 기반 제품이고, 사용자는 브라우저를 통해 서버에 접속한다. 따라서 coding agent가 직접 다뤄야 하는 대상은 사용자의 개인 PC 폴더가 아니라, 서버가 turn/job 단위로 준비한 `격리된 repo workspace`여야 한다.

이번 작업의 본질은 아래 세 가지를 동시에 정리하는 것이다.

- repo 소스를 웹 제품에서 어떻게 받는가
- 받은 repo를 어떤 단위로 서버 작업공간에 materialize 하는가
- 그 작업공간 안에서만 `coding_team`이 어떤 도구를 어떤 권한으로 사용할 것인가

## 목표

- 웹 제품에서 사용할 수 있는 `repo ingress`를 도입한다.
- thread 단위로 "이 대화가 어떤 repo를 다루는지"를 추적할 수 있게 한다.
- turn/job 단위 `isolated workspace`를 생성하고, coding tool은 그 경로 안에서만 동작하게 만든다.
- `coding_team`을 `codebase_explorer -> implementation_engineer -> runtime_verifier(optional) -> reviewer` 구조로 추가한다.
- 기존 trace/tool log/artifact 수집 경로를 coding 작업에도 재사용한다.
- E2E 검증은 Playwright 기반 실제 웹 시나리오로 마무리한다.

## 비목표

- 사용자의 개인 PC 파일시스템을 웹앱이 직접 수정하는 기능
- 완전 unrestricted shell 제공
- private repo OAuth 전체 제품화
- 대규모 병렬 멀티 repo orchestration
- 복잡한 edge case 위주의 테스트 코드 작성

## 현재 상태와 제약

### 1. 현재 `file_io`는 프로덕션용 coding workspace 모델이 아니다

- `packages/agent-tools/src/agent_tools/file_io.py`
  - 전역 `AGENT_WORKSPACE` 또는 `/tmp/agent_workspace`를 사용한다.
  - 이 방식은 멀티유저, 멀티스레드, 멀티턴 격리에 부적합하다.

### 2. turn 단위 runtime workspace 패턴은 이미 존재한다

- `apps/backend/services/storage_service.py`
  - `create_analysis_workspace(thread_id, turn_id)`가 `workspace/`와 `artifacts/`를 생성한다.
- `apps/backend/api/routes/chat.py`
  - turn 시작 시 `ToolRuntimeContext`에 `workspace_dir`, `artifact_dir`를 세팅한다.
- `packages/agent-tools/src/agent_tools/runtime.py`
  - artifact는 runtime workspace/artifact root 내부 경로만 허용한다.

즉, coding team은 새로운 workspace 철학을 만들기보다, 이 패턴을 repo 작업에 맞게 일반화하는 것이 맞다.

### 3. 현재 웹 UI에는 repo ingress가 없다

- Playwright preflight 기준:
  - `dong / dong1!` 로그인 정상
  - thread list, 새 대화, 메시지 입력창, `Add files` 버튼 존재
- 그러나 현재 첨부 허용 형식은 다음뿐이다.
  - `image/*,.pdf,.xlsx,.csv,.json,.docx`
- 따라서 `repo zip`은 현행 업로드 entry로는 받을 수 없다.

### 4. 현재 상위 그래프에 `coding_team`이 없다

- `apps/backend/workflow/main_graph.py`
  - 현재 팀은 `research_team`, `writing_team`, `vision_team`, `data_science_team`
- `packages/agent-core/src/agent_core/builder.py`
  - 새 팀을 추가하기 좋은 공통 구조는 이미 존재

## 핵심 아키텍처 결정

| 결정 항목 | 채택 방향 | 이유 |
| --- | --- | --- |
| repo source | `GitHub URL`, `generic git URL`, `repo zip upload`, `server-registered repo` | 웹 제품에서 현실적으로 받을 수 있는 ingress만 허용 |
| repo binding scope | `thread` 단위 | 여러 turn에서 같은 repo 문맥을 이어갈 수 있어야 함 |
| workspace scope | `turn/job` 단위 | 수정/검증 실행은 매 turn 격리되어야 안전함 |
| workspace layout | `repo/`, `artifacts/`, `logs/` | 코드, 산출물, 실행 로그를 분리 |
| tool root | current turn workspace root only | repo 밖 파일 접근 차단 |
| coding route trigger | repo source 존재 + coding intent | 일반 질문과 coding 작업을 명확히 분리 |
| verifier | reviewer + runtime verifier | 코드 수정 후 실제 검증을 강제하기 위함 |

## 제안 아키텍처

### 1. 데이터/상태 모델

| 엔터티 | 역할 | 최소 필드 |
| --- | --- | --- |
| `thread_repository_bindings` | 어떤 thread가 어떤 repo를 다루는지 기록 | `id`, `thread_id`, `user_id`, `source_type`, `source_ref`, `display_name`, `default_branch`, `pinned_commit_sha`, `status`, `created_at`, `updated_at` |
| `workspace_jobs` | 각 turn/job의 materialized workspace 기록 | `id`, `thread_id`, `turn_id`, `binding_id`, `workspace_path`, `artifact_path`, `log_path`, `repo_commit_sha`, `status`, `created_at`, `completed_at` |
| `chat_turns.metadata_json` 확장 | coding 검증 메타데이터 | `repo_binding_id`, `workspace_job_id`, `changed_files`, `test_summary` |

원칙:

- thread는 "무슨 repo를 다루는가"를 기억한다.
- turn은 "이번 실행에서 어떤 workspace를 만들었는가"를 기억한다.
- 실제 코드 수정은 turn workspace에서만 일어난다.

### 2. API / ingress 계약

권장 ingress는 아래 네 가지다.

| ingress | 형태 | 용도 |
| --- | --- | --- |
| GitHub URL | URL 입력 | public repo, 향후 private repo 확장 |
| generic git URL | URL 입력 | GitHub 외 git provider 대응 |
| repo zip upload | zip 업로드 | 작은 프로젝트/샘플 코드 |
| server-registered repo | 내부 ID 선택 | dogfooding / 운영 전용 |

권장 API surface:

- `POST /api/repositories/bind`
  - thread에 repo source를 연결
- `GET /api/repositories/bindings/{thread_id}`
  - 현재 thread repo binding 조회
- `DELETE /api/repositories/bindings/{binding_id}`
  - binding 해제
- `POST /api/repositories/materialize`
  - 필요 시 repo를 workspace로 clone/extract

채팅 요청은 아래 중 하나를 사용한다.

- 채팅 전에 binding을 만들어두고 `thread_id`로 참조
- 또는 첫 coding 요청에서 repo source payload를 함께 보내고, 서버가 binding을 생성

권장 방향은 `binding 선생성`이다. UI와 API가 더 명료해진다.

### 3. workspace lifecycle

| 단계 | 동작 |
| --- | --- |
| bind | thread에 repo source 저장 |
| materialize | repo를 서버 로컬 staging/cache에 clone 또는 unzip |
| hydrate workspace | turn 시작 시 staging snapshot을 새 turn workspace로 복사 |
| execute | coding tools가 workspace 내부에서만 read/edit/exec |
| collect | diff, changed files, test output, screenshots, logs 수집 |
| finalize | 응답에 요약/검증 결과 첨부 |
| cleanup | TTL 기반 삭제 또는 짧은 기간 보관 |

권장 디렉토리:

```text
apps/backend/data/workspaces/
  user_{user_id}/
    thread_{thread_id}/
      turn_{turn_id}/
        repo/
        artifacts/
        logs/
```

### 4. coding team 구조

| 워커 | 역할 | 허용 도구 |
| --- | --- | --- |
| `codebase_explorer` | 관련 파일/심볼/구조 파악 | `read`, `search`, `list` |
| `implementation_engineer` | 실제 코드 수정과 기본 검증 | `read`, `search`, `edit`, `test`, `build`, `lint`, `git_read` |
| `runtime_verifier` | 로컬 실행/브라우저 검증 | `exec`, `playwright`, `logs`, `artifact_read` |
| `reviewer` | 수정 결과가 요청을 만족하는지 점검 | validator node 재사용 |

기본 흐름:

1. `codebase_explorer`
2. `implementation_engineer`
3. `reviewer`
4. 필요 시 `runtime_verifier`
5. `FINISH`

### 5. coding tool contract

| 계층 | 예상 도구 | 정책 |
| --- | --- | --- |
| Read/Search | `read_file`, `search_code`, `list_tree` | 기본 허용 |
| Edit | `apply_patch_edit`, `create_file` | workspace root 한정 |
| Execute | `run_tests`, `run_lint`, `run_build`, `run_dev_server` | allowlisted command만 허용 |
| Browser | `verify_ui_playwright` | 로컬 dev server 대상 위주 |
| Git Read | `git_status`, `git_diff`, `git_log` | 기본 허용 |
| Git Write | `git_commit`, `git_branch`, `git_apply` | V1 제외 또는 엄격 제한 |
| Docs/Web | `fetch_official_docs` | 조건부 허용 |
| External MCP | `github/*`, `playwright/*` 등 | V1 후순위 |

## 설계 원칙

### 1. repo binding과 workspace execution을 분리한다

- binding은 thread 수준의 지속 정보
- workspace는 turn 수준의 일회성 실행 환경

### 2. repo 밖 접근을 금지한다

- 모든 edit/exec는 current turn workspace root 내부로 제한
- artifact도 workspace/artifact root 내부 경로만 허용

### 3. coding intent가 있을 때만 `coding_team`으로 라우팅한다

최소 조건:

- repo binding 존재
- 사용자의 최신 요청에 code modification / debug / fix / refactor / test intent 존재

### 4. 테스트 코드는 happy path 최소 세트만 둔다

이번 작업에서는 edge case 중심 테스트를 쓰지 않는다. 테스트 코드는 다음 원칙을 따른다.

- repo binding 생성 성공
- workspace 생성 성공
- coding route 정상 선택
- coding tool root restriction 정상 동작
- 기본 수정/검증 흐름 정상 완료

즉, `필수 구조가 살아있는지`만 짧고 간결하게 검증한다.

## 테스트 전략

## 테스트 코드 작성 원칙

| 원칙 | 적용 방식 |
| --- | --- |
| edge case 미포함 | 인증 실패, zip corruption, 네트워크 타임아웃 등은 이번 테스트 코드 범위에서 제외 |
| happy path 중심 | bind -> materialize -> route -> edit -> verify 핵심 흐름만 검증 |
| 짧은 테스트 | mock/stub를 적극 사용해 한 테스트가 한 계약만 검증 |
| 회귀 봉합 우선 | routing/tool root/API contract가 깨지지 않는지 위주 |

### 백엔드 최소 테스트

| 테스트 파일 | 필수 검증 |
| --- | --- |
| `test_repository_binding_api.py` | GitHub URL 또는 zip source binding CRUD |
| `test_workspace_manager.py` | thread/turn 기준 workspace 생성과 경로 구조 |
| `test_coding_team_wiring.py` | `main_graph`에 `coding_team`이 연결되고 prompt wiring이 맞는지 |
| `test_coding_supervisor.py` | repo binding + coding intent에서 `coding_team`으로 가는지 |
| `test_coding_tools.py` | read/edit/exec tool이 workspace root 안에서만 동작하는지 |
| `test_chat_api_coding_flow.py` | coding turn 시작 시 workspace context가 실리는지 |

### 프런트엔드 최소 테스트

| 테스트 파일 | 필수 검증 |
| --- | --- |
| `repo-binding-panel.test.tsx` | GitHub URL / zip attach UI가 보이고 submit 되는지 |
| `page.test.tsx` 또는 분리 파일 | repo binding이 있는 thread에서 coding prompt submit이 가능한지 |
| `thread-header.test.tsx` | 현재 thread의 bound repo 정보가 노출되는지 |

### 검증 커맨드

- 백엔드
  - `cd apps/backend && uv run pytest tests/test_repository_binding_api.py tests/test_workspace_manager.py tests/test_coding_team_wiring.py tests/test_coding_supervisor.py tests/test_coding_tools.py tests/test_chat_api_coding_flow.py -v`
- 프런트엔드
  - `cd apps/frontend && npm run lint`
  - `cd apps/frontend && npm run test -- repo-binding`
  - `cd apps/frontend && npm run build`

## Playwright E2E 검증 계획

### 사전 원칙

- 실제 E2E는 구현 완료 후 수행한다.
- trajectory는 2~3개만 유지한다.
- 각 trajectory는 happy path만 검증한다.
- 예상 step과 expected observable을 사전에 명시한다.

### Trajectory 1. Local Git URL Python Bug Fix

목적:

- local `file://` git URL 기반 repo ingress와 coding 기본 루트를 검증

입력:

- repo source: local `file://` git URL
- prompt: `이 저장소에서 python -m unittest failing test를 고쳐줘. 수정 후 같은 명령으로 다시 확인해줘.`

예상 흐름:

1. repo binding 생성
2. workspace materialize
3. `coding_team` 진입
4. `codebase_explorer`
5. `implementation_engineer`
6. 관련 테스트 실행
7. reviewer 통과
8. diff + 테스트 결과 포함 응답

Playwright 관찰 포인트:

- repo source가 thread UI에 표시됨
- timeline에 coding team 단계가 표시됨
- 최종 응답에 changed files / test result가 포함됨

### Trajectory 2. Repo Zip Upload Bug Fix

목적:

- zip ingress happy path 검증

입력:

- repo source: zip 업로드
- prompt: `이 저장소에서 python -m unittest failing test를 고쳐줘. 수정 후 같은 명령으로 다시 확인해줘.`

예상 흐름:

1. zip 업로드 성공
2. repo binding 생성
3. workspace extract
4. coding team 수정
5. unittest 실행
6. 응답에 수정 파일과 검증 결과 포함

Playwright 관찰 포인트:

- zip 업로드 UI가 정상 동작
- 업로드된 repo가 thread context에 표시됨
- 최종 응답에 수정 파일과 unittest 결과가 표시됨

## Playwright 사전 확인 결과

2026-03-31 기준 preflight 확인:

- `dong / dong1!` 로그인 성공
- 메인 workspace 진입 성공
- thread list, `New Chat`, message input, `Add files` 버튼 존재
- 현재 업로드 input은 `zip`을 허용하지 않음
- 따라서 repo zip ingress는 새 input surface 또는 accept 확장이 필요함

이 확인은 구현 전 계획 타당성 검토용이며, 실제 coding trajectory 검증은 구현 완료 후 위 2개 trajectory로 수행한다.

## Playwright 실제 검증 결과

- Trajectory 1
  - local `file://` git URL binding 성공
  - UI에서 `coding_team -> codebase_explorer -> implementation_engineer -> finalizer -> completed` 흐름 확인
  - 최종 응답에 `calculator.py` 수정, `python -m unittest`, `Exit code: 0`, `git diff` artifact 노출 확인
- Trajectory 2
  - zip 업로드 binding 성공
  - UI에서 `coding_team -> codebase_explorer -> implementation_engineer -> finalizer -> completed` 흐름 확인
  - 최종 응답에 `text_utils.py` 수정, `python -m unittest PASS`, `git diff` artifact 노출 확인

## Phase 1. Repo Source Contract and Thread Binding

- [x] `thread_repository_bindings` 데이터 모델과 service를 추가한다.
- [x] GitHub URL / generic git URL / server-registered repo / zip repo source 타입을 정의한다.
- [x] repo source validation 규칙을 추가한다.
- [x] thread에 repo binding을 생성/조회/해제하는 API를 추가한다.
- [x] 최소 API 테스트를 추가한다.

완료 기준:

- thread가 하나의 active repo binding을 가질 수 있다.
- GitHub URL happy path binding이 동작한다.

## Phase 2. Workspace Manager and Runtime Context Generalization

- [x] turn 기준 `repo/`, `artifacts/`, `logs/` workspace를 생성하는 workspace manager를 추가한다.
- [x] staging clone/extract와 turn workspace hydrate 경로를 구현한다.
- [x] 기존 `ToolRuntimeContext`를 coding workspace에도 사용할 수 있게 일반화한다.
- [x] coding artifact/diff/log 수집 경로를 추가한다.
- [x] 최소 workspace manager 테스트를 추가한다.

완료 기준:

- coding turn 시작 시 workspace가 생성된다.
- tool이 workspace 외부 경로를 사용하지 못한다.

## Phase 3. Coding Team Graph, Prompt, and Routing

- [x] `packages/prompt-kit`에 coding team supervisor/worker prompt를 추가한다.
- [x] `apps/backend/workflow/teams/coding.py`를 추가한다.
- [x] `main_graph.py`에 `coding_team`을 등록한다.
- [x] head supervisor routing 규칙에 repo binding + coding intent 경로를 추가한다.
- [x] reviewer/runtime verifier 연결을 마무리한다.
- [x] 최소 wiring/routing 테스트를 추가한다.

완료 기준:

- repo binding이 있는 coding 요청은 `coding_team`으로 간다.
- coding team 내부 흐름이 `explorer -> implementation -> reviewer`를 기본으로 따른다.

## Phase 4. Coding Tools V1

- [x] `read/search/list` 계층 도구를 추가한다.
- [x] workspace root 한정 `apply_patch_edit`를 추가한다.
- [x] `run_tests`, `run_lint`, `run_build`, `run_dev_server`를 allowlisted command 방식으로 추가한다.
- [x] `git_status`, `git_diff`, `git_log` 읽기 계층 도구를 추가한다.
- [x] Playwright 검증 도구를 coding runtime 경로에 연결한다.
- [x] 최소 coding tool 테스트를 추가한다.

완료 기준:

- implementation worker가 workspace 안 파일을 수정할 수 있다.
- verifier가 테스트 또는 브라우저 검증을 수행할 수 있다.

## Phase 5. Web UI Repo Ingress and Thread UX

- [x] thread 화면에 repo binding panel을 추가한다.
- [x] GitHub URL 입력, zip 업로드, 현재 bound repo 표시를 구현한다.
- [x] coding turn 중 repo context가 사용자에게 보이도록 한다.
- [x] coding 결과의 changed files / test summary / artifact 링크 표시를 추가한다.
- [x] 최소 프런트 테스트를 추가한다.

완료 기준:

- 웹 UI에서 repo를 연결하고 coding 요청을 시작할 수 있다.
- 사용자는 현재 어떤 repo를 대상으로 작업 중인지 볼 수 있다.

## Phase 6. End-to-End Verification

- [x] 백엔드 최소 테스트 세트를 모두 통과시킨다.
- [x] 프런트 lint/test/build를 모두 통과시킨다.
- [x] Playwright로 Trajectory 1을 직접 수행하고 예상 흐름을 확인한다.
- [x] Playwright로 Trajectory 2를 직접 수행하고 zip ingress 흐름을 확인한다.
- [x] trajectory별 실제 결과와 기대 결과를 plan 또는 docs에 기록한다.

완료 기준:

- 2~3개의 happy path trajectory가 실제 웹 UI에서 끝까지 재현된다.
- 최종 응답에 diff/검증 결과/artifact 정보가 표시된다.

## 최종 완료 기준

- `coding_team`이 상위 그래프의 정식 팀으로 등록된다.
- repo source를 웹에서 입력할 수 있다.
- thread는 active repo binding을 가진다.
- coding turn은 격리된 server-side workspace에서만 실행된다.
- coding tool은 workspace root 안에서만 동작한다.
- 최소 테스트 세트와 Playwright trajectory 검증이 모두 통과한다.
