---
작업명: Coding Team Control Plane And UI Plan
간단요약: coding_team의 권한 정책, 실행 요약 스키마, 라이브 및 히스토리컬 UI 노출을 강화해 안전성과 가시성을 함께 끌어올린다.
작성일시: 2026-04-07 17:00 KST
최종 수정일시: 2026-04-07 17:00 KST
---

# Coding Team Control Plane And UI Plan

## 목표

- `coding_team`의 현재 “동작은 하지만 정책이 느슨한” 상태를 운영 가능한 수준으로 올린다.
- repo-bound coding turn의 권한 정책을 읽기/쓰기/실행 기준으로 분리한다.
- 백엔드에 저장되는 coding 실행 결과를 구조화해 프런트가 안정적으로 hydrate할 수 있게 한다.
- 사용자가 라이브 turn과 저장된 thread 모두에서 “무엇을 바꿨고, 무엇을 검증했고, 무엇이 아직 미확인인지”를 즉시 이해할 수 있게 만든다.
- 기존 generic workspace UX를 깨지 않고 coding 전용 정보만 정밀하게 얹는다.

## 비목표

- repo ingress를 다시 설계하지 않는다.
- thread binding 또는 turn workspace의 근본 구조를 다시 만들지 않는다.
- V1에서 full tool-by-tool historical replay를 구현하지 않는다.
- unrestricted shell 또는 무제한 MCP 실행을 허용하지 않는다.
- 기존 generic telemetry 패널을 coding 전용 화면으로 분리하지 않는다.

## 배경

현재 구현은 이미 아래를 갖고 있다.

- thread 단위 repo binding
- turn 단위 isolated workspace
- `codebase_explorer -> implementation_engineer -> runtime_verifier` 구조
- workspace 내부 경로 제한
- allowlisted command 실행
- trace/tool event/turn metadata 저장
- 공용 workspace UI에서 `route/tool/reasoning/checkpoint` 스트림 렌더링

하지만 운영성과 UX 관점에서 중요한 공백이 남아 있다.

- repo-bound coding turn에서 approval guard가 사실상 꺼진다.
- `workspace_summary`가 저장되지만 프런트에서 거의 소비되지 않는다.
- runtime verification이 localhost fetch 중심이라 이름에 비해 약하다.
- historical thread에서 coding 작업의 결과 요약이 충분히 복원되지 않는다.
- 편집 도구가 exact snippet replace 중심이라 복잡한 수정에 취약하다.

## 전제

- 기존 `plans/CODING_TEAM_REPO_WORKSPACE_PLAN.md`의 ingress/workspace 기본 방향은 유지한다.
- 기존 `plans/FIGMA_WORKSPACE_UI_REFACTOR_PLAN.md`의 3열 workspace shell은 유지한다.
- 시스템 프롬프트 추가/수정은 반드시 `packages/prompt-kit`에서 수행한다.
- worker capability와 tool policy는 분리해서 다룬다.
- 프런트는 raw trace viewer가 아니라 user-facing execution summary 중심으로 진화한다.

## 핵심 결정

| 결정 항목 | 채택 방향 | 이유 |
| --- | --- | --- |
| approval 정책 | `read_only`는 무중단, `workspace_write`와 `workspace_execute`는 정책 기반 승인 가능 | 현재 repo-bound bypass를 완화해야 함 |
| tool 정책 단위 | worker allowlist + tool permission tier 이중 구조 | prompt만으로는 통제가 약함 |
| coding summary 저장 | typed summary contract로 저장 | 프런트 historical hydrate와 audit에 필요 |
| 라이브 UI 노출 | 중앙 compact strip + 우측 coding summary cards | 채팅 본문 오염 없이 핵심 상태 전달 |
| historical UI 노출 | full replay 대신 summary hydrate 우선 | 구현 복잡도 대비 효과가 큼 |
| runtime verifier | localhost text check에서 browser verify 계층으로 점진 확장 | “화면 확인” 요청 대응력 보강 |
| edit primitive | exact replace 단일 방식에서 structured patch 계층으로 확장 | 현실적인 리포 작업 대응 필요 |

## 대상 구조

### 백엔드

- `packages/agent-tools/src/agent_tools/coding.py`
- `packages/agent-core/src/agent_core/supervisor.py`
- `apps/backend/api/routes/chat.py`
- `apps/backend/services/repository_workspace_service.py`
- `apps/backend/services/chat_analytics_service.py`
- `apps/backend/services/thread_service.py`
- `packages/prompt-kit/src/prompt_kit/prompts.py`

### 프런트엔드

- `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx`
- `apps/frontend/src/components/workspace/LiveToolStatusStrip.tsx`
- `apps/frontend/src/components/sidebar/AgentTimeline.tsx`
- `apps/frontend/src/components/workspace/RepositoryBindingPanel.tsx`
- 새 coding summary 전용 컴포넌트들

## 정보 설계 원칙

### 중앙 패널

- 최종 assistant 답변
- 현재 단계에 대한 짧은 live strip
- 필요한 경우 artifact 링크

### 우측 패널

- `Agent Timeline`
- `Inner Monologue`
- `Coding Change Set`
- `Verification Status`
- `Execution Policy`
- `Suggested Queries`

### historical thread

- full trace replay 대신 아래만 복원
- 마지막 변경 파일
- 마지막 검증 결과
- 마지막 artifact
- 마지막 approval 여부
- unavailable한 정보는 명시적으로 표시

## 데이터 계약

### CodingSummary 계약

최소 필드:

- `repo_binding_id`
- `workspace_job_id`
- `repo_commit_sha`
- `permission_mode`
- `approval_required`
- `approval_state`
- `changed_files`
- `git_status`
- `commands_run`
- `verification_results`
- `generated_artifacts`
- `runtime_verification`
- `failure_summary`
- `completed_at`

### VerificationResult 계약

최소 필드:

- `kind`
  - `test`
  - `lint`
  - `build`
  - `runtime`
- `label`
- `status`
  - `passed`
  - `failed`
  - `skipped`
  - `unverified`
- `command`
- `log_artifact_path`
- `summary`

### PermissionTier 계약

최소 tier:

- `read_only`
- `workspace_write`
- `workspace_execute`
- `browser_verify`
- `external_mcp`
- `dangerous`

## 실행 정책 원칙

- `codebase_explorer`는 `read_only`만 사용한다.
- `implementation_engineer`는 `workspace_write`, `workspace_execute`를 사용할 수 있다.
- `runtime_verifier`는 `workspace_execute`, `browser_verify`를 사용할 수 있다.
- destructive class tool은 별도 명시적 정책 없이 허용하지 않는다.
- repo-bound coding turn이라고 해서 approval을 전면 우회하지 않는다.
- 최소 기준:
  - 읽기/탐색은 자동 허용
  - 파일 수정은 정책 승인 가능
  - 명령 실행은 정책 승인 가능
  - browser verify는 별도 tier로 추적

## Phase 0. 계약 고정

- [ ] 새 계획 문서를 `plans/CODING_TEAM_CONTROL_PLANE_AND_UI_PLAN.md`로 추가한다.
- [ ] `coding summary`와 `verification result`의 canonical schema를 문서화한다.
- [ ] permission tier와 approval matrix를 문서화한다.
- [ ] 라이브 UI와 historical UI의 정보 위계를 문서화한다.
- [ ] 기존 coding workspace plan과 역할 경계가 충돌하지 않는지 확인한다.

검증:

- [ ] 기존 `plans/CODING_TEAM_REPO_WORKSPACE_PLAN.md`와 중복 또는 충돌이 없는지 점검
- [ ] 기존 workspace UI 계약과 충돌이 없는지 점검

## Phase 1. 정책 엔진과 훅 계층 도입

- [ ] coding tool별 permission tier 선언 구조를 추가한다.
- [ ] worker allowlist와 tool tier를 함께 평가하는 policy resolver를 추가한다.
- [ ] `pre_command_policy_hook`를 추가한다.
- [ ] `pre_patch_guard_hook`를 추가한다.
- [ ] `post_command_summary_hook`를 추가한다.
- [ ] `post_patch_diff_hook`를 추가한다.
- [ ] repo-bound coding turn의 unconditional approval bypass를 제거하고 새 approval matrix를 적용한다.
- [ ] 승인 발생 시 trace와 turn metadata에 decision reason을 저장한다.

검증:

- [ ] backend pytest: policy resolver
- [ ] backend pytest: repo-bound read-only request는 승인 없이 진행
- [ ] backend pytest: file write request는 승인 경로 진입
- [ ] backend pytest: command execution request는 승인 경로 진입
- [ ] backend pytest: blocked command와 blocked patch guard 확인

## Phase 2. Coding Summary 백엔드 구조화

- [ ] `workspace_summary`를 느슨한 dict가 아니라 typed builder로 교체한다.
- [ ] `changed_files`, `git_status`, `commands_run`, `verification_results`, `artifacts`를 구조화해 저장한다.
- [ ] turn finalize 시 `coding_summary` projection을 metadata에 일관되게 쓴다.
- [ ] thread 또는 historical hydrate용 summary 조회 helper를 추가한다.
- [ ] failure와 skipped verification을 구분해 저장한다.

검증:

- [ ] backend pytest: coding summary projection 생성
- [ ] backend pytest: changed_files 저장
- [ ] backend pytest: verification result 저장
- [ ] backend pytest: failure summary 저장
- [ ] backend pytest: historical retrieval 가능 여부 확인

## Phase 3. 라이브 Coding UX 도입

- [ ] `LiveToolStatusStrip`를 coding-aware 상태 문구 중심으로 개선한다.
- [ ] 우측 패널에 `CodingChangeSetCard`를 추가한다.
- [ ] 우측 패널에 `VerificationStatusCard`를 추가한다.
- [ ] 우측 패널에 `ExecutionPolicyCard`를 추가한다.
- [ ] 중앙 assistant 영역에는 “현재 수정/검증 상태”를 짧게 보여주는 compact copy만 남긴다.
- [ ] approval이 필요한 경우, 왜 멈췄는지 한 줄 요약을 먼저 보여준다.
- [ ] artifact가 있으면 summary card와 assistant 본문 둘 다에서 접근 가능하게 한다.

검증:

- [ ] frontend test: `route/tool/reasoning/checkpoint`와 coding summary state 결합
- [ ] frontend test: changed files card 렌더
- [ ] frontend test: verification `passed/failed/skipped/unverified` 상태 렌더
- [ ] frontend test: approval required copy 렌더
- [ ] frontend test: artifact link 렌더
- [ ] `npm run lint`
- [ ] `npm run build`

## Phase 4. Historical Coding Summary Hydration

- [ ] saved thread 선택 시 마지막 coding summary를 hydrate하는 경로를 추가한다.
- [ ] historical sidebar에 `Last Change Set` 섹션을 추가한다.
- [ ] historical sidebar에 `Last Verification` 섹션을 추가한다.
- [ ] historical sidebar에 `Last Artifacts` 섹션을 추가한다.
- [ ] full tool replay 미지원 상태는 유지하되, summary 기반 복원으로 대체한다.
- [ ] unavailable 정보는 명시적 fallback copy로 처리한다.

검증:

- [ ] backend pytest: historical coding summary retrieval
- [ ] frontend test: saved thread 선택 시 summary hydrate
- [ ] frontend test: replay unavailable copy와 summary 공존 확인

## Phase 5. Runtime Verifier 강화

- [ ] `browser_verify` tier를 정식 도입한다.
- [ ] Playwright 기반 verifier 도입 범위를 확정한다.
- [ ] dev server start, URL, expected selector 또는 text, screenshot artifact를 구조화한다.
- [ ] runtime verification 결과를 `verification_results`에 통합한다.
- [ ] console 또는 network failure를 artifact로 저장한다.

검증:

- [ ] backend pytest: browser verification request wiring
- [ ] frontend test: runtime verification status 렌더
- [ ] 수동 검증: 실제 UI 확인 요청 시 screenshot과 log link 확인

## Phase 6. Edit Primitive 확장

- [ ] `apply_patch_edit`의 exact replace 한계를 문서화한다.
- [ ] multi-hunk patch primitive를 추가한다.
- [ ] rename 또는 delete 필요 여부를 별도 tool로 분리할지 결정한다.
- [ ] edit 결과를 structured diff 중심으로 요약하는 경로를 추가한다.

검증:

- [ ] backend pytest: multi-hunk patch
- [ ] backend pytest: rename 또는 delete 정책
- [ ] backend pytest: structured diff summary 생성

## 위험 요소

- approval 정책을 바꾸면 현재 coding flow UX가 느려질 수 있다.
- summary schema를 성급히 넓히면 프런트와 백엔드가 동시에 흔들릴 수 있다.
- runtime verifier를 browser 기반으로 올릴 때 환경 의존성이 증가한다.
- historical hydrate를 무리하게 full replay로 확장하면 범위가 급격히 커진다.

## 완화 전략

- approval 정책은 `read_only` 무중단 원칙을 유지한다.
- summary schema는 Phase 0에서 먼저 고정하고 이후 additive change만 허용한다.
- browser verify는 Phase 5로 분리하고 earlier phase와 독립 검증 가능하게 둔다.
- historical replay는 summary hydrate까지만 V1 범위로 묶는다.

## 검증 방법

### 백엔드

- `cd apps/backend`
- `uv run pytest tests/test_coding_supervisor.py -v`
- `uv run pytest tests/test_chat_api_coding_flow.py -v`
- `uv run pytest tests/test_coding_tools.py -v`
- 새 policy, summary, historical 관련 테스트 추가 후 통과 확인

### 프런트엔드

- `cd apps/frontend`
- `npm run lint`
- `npm run test`
- `npm run build`

### 수동 시나리오

- [ ] read-only repo 질문
- [ ] single-file patch 요청
- [ ] failing test fix 요청
- [ ] runtime 또는 UI 확인 포함 요청
- [ ] approval reject 후 재시도
- [ ] saved thread 재진입 후 coding summary 확인

## 완료 기준

- 사용자가 라이브 coding turn에서 변경 파일과 검증 상태를 즉시 볼 수 있다.
- 사용자가 저장된 coding thread에서 마지막 변경/검증 요약을 다시 볼 수 있다.
- repo-bound coding turn의 권한 정책이 더 이상 implicit bypass가 아니다.
- runtime verification 결과가 “실행했다” 수준이 아니라 “무엇을 확인했고 무엇이 남았는지”로 구조화된다.
- coding team의 backend control plane과 frontend 표현이 같은 contract를 공유한다.
