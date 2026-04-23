---
작업명: Coding Agent MiniMax-Inspired UI Plan (PoC-minimal, aside-only)
간단요약: MiniMax Agent의 UI 디자인 포인트를 PoC 수준으로만 차용. drawer/신규 SSE 이벤트/Plan tracker/Terminal stream 등 고도화는 전부 제거하고, "우측 aside Coding 탭 하나에 모든 coding 시각화를 통합"하는 단일 스크롤 구조만 구현한다.
작성일시: 2026-04-23 19:20 KST
최종 수정일시: 2026-04-23 20:15 KST
---

# Coding Agent MiniMax-Inspired UI Plan (PoC-minimal, aside-only)

## 목표

- coding_team 분기일 때 사용자가 **"뭐가 바뀌었고 뭐가 만들어졌는지"를 우측 aside 한 곳에서** 스크롤만으로 확인.
- 신규 SSE 이벤트·supervisor 로직 수정·터미널 스트리밍·drawer·Plan tracker는 **전부 범위 밖**.
- "MiniMax처럼 생겼다" 체감을 주는 최소 디자인 요소(파일 tree · diff · artifact preview)만 기존 Coding 카드들과 같은 aside 안에 병합.

## 비목표

- 중앙 하단 drawer (이전 계획에 있었으나 세로 공간 예산 초과 + 기존 Change Set 카드와 중복이라 **삭제**)
- Plan(Todo) tracker / supervisor JSON 선언 (agent-core 변경 부담)
- Terminal 출력 실시간 스트림
- 새 SSE event type (`plan_update`, `terminal_output`)
- attachments 이벤트 inline payload 확장 (별도 plan으로 이월)
- Lightning/Pro toggle, Branch sessions, Selector editor, iframe preview

## 결정된 구조 (3-agent 리뷰 반영)

| 리뷰 영역 | 이전 결정 | 리뷰 후 최종 |
| :--- | :--- | :--- |
| Coding 정보 배치 | aside 탭 + 중앙 하단 drawer 2원화 | **aside Coding 탭 단일 스크롤만** |
| Change Set 카드 | 유지 | `RepoTreePanel`로 **흡수·대체** (changed_files 하이라이트) |
| drawer `Files/Preview` 탭 | 구현 | **삭제** |
| attachments inline payload | Phase로 포함 | **별도 plan 이월** (`CODING_AGENT_ATTACHMENT_INLINE_PREVIEW_PLAN.md`) |
| historical hydrate | 독립 Phase | Phase 0/1의 `from_turn_metadata` projection으로 **자동 처리** |
| git diff 수집 | 파일마다 `git diff <path>` 반복 | **단일 `git diff --unified=3 --no-color` + 파일 추출** |
| state 필드 | `activeRightTab`·`drawerOpen`·`drawerTab` | `activeRightTab` **한 개만** |
| 신규 컴포넌트 | 5개 (CodingAsideTabs/CodingDrawer/RepoTreePanel/CodingDiffModal/InlineArtifactPreview) | **2개** (`CodingAsideTabs`, `RepoTreePanel`) + `CodingChangeSetCard` 삭제 |

**근거 리뷰 문서**: `_workspace/plan_review_frontend.md`, `_workspace/plan_review_backend.md`, `_workspace/plan_review_qa.md`.

## 사전 작업 (계획 시작 전 선처리)

- [ ] `LiveToolStatusStrip`의 coding 툴 문구 매핑 버그 수정 (`_workspace/ui_ux_before_after_report.md:44` 기록). `tool.name`이 display_name(`Run Repo Command`)으로 들어와 `CODING_TOOL_COPY[snake_case]` 매칭 실패. 원본 `tool_name` 보존 또는 양쪽 키 매칭 추가.

## 배경 (MiniMax에서 가져올 것 간략)

MiniMax Agent의 UX 시그니처 중 PoC에서 **흉내낼 가치** vs **보류**:

| 패턴 | 채택 | 비고 |
| :--- | :---: | :--- |
| persistent file directory | ✅ | aside Coding 탭의 `RepoTreePanel` |
| clickable file → preview(diff) | ✅ | tree row 클릭 → 간단 inline diff(`<details><pre>`) |
| code diff view | ✅ | PoC는 `<pre>` + +/- 라인 색상만, 라이브러리 없이 |
| artifact preview | ⏸ | 별도 plan으로 이월 |
| live running log | ✅ (이미 구현됨) | `LiveToolStatusStrip` + 생성-중 인디케이터 |
| Plan(Todo) / Terminal / Branch / Selector | ⏸ | 범위 밖 |

공통 트렌드 (2026 웹 조사): **"Minimal Context Engineering — 모든 것을 보여주지 않고 high-signal만 노출"** — 본 계획의 축약 방향과 정렬.

## 전제

- `plans/CODING_TEAM_CONTROL_PLANE_AND_UI_PLAN.md`의 Phase 0 데이터 계약(`CodingSummary` 등)을 그대로 재사용.
- 백엔드 변경은 `services/repository_workspace_service.py` + `schemas/coding.py` 두 파일.
- 신규 SSE 이벤트 0건. attachments 이벤트 shape도 본 계획에서 **변경하지 않음**.
- 프롬프트 수정 0건.
- 모든 coding 전용 UI는 `hasCodingSignal(activeThreadState.codingSummary) || activeThreadState.repoBinding != null` 가드.

## 정보 설계

### 중앙 컬럼 (변화 없음)
- 채팅 + 입력창
- `LiveToolStatusStrip` + 생성-중 인디케이터
- `RepositoryBindingPanel` (바인딩 전만 펼침)

### 우측 aside — 탭 2개
- **Reasoning** 탭: 기존 `AgentTimeline` + `ReasoningSummaryPanel` + `SuggestedQueriesPanel`
- **Coding** 탭: 신규 순서
  1. `RepoTreePanel` (변경 파일 하이라이트 + row 클릭 → 인라인 diff 펼침)
  2. `VerificationStatusCard` (기존, 데이터 없을 때 숨김)
  3. `ExecutionPolicyCard` (기존)
  - **`CodingChangeSetCard`는 제거** — `RepoTreePanel`이 changed_files를 흡수

### 기본 탭 규칙
- `hasCodingSignal || repoBinding != null` → `Coding`
- 그 외 → `Reasoning`

### 탭 상태 persistence
- **per-thread session only** (페이지 리로드 시 기본 규칙으로 돌아감). localStorage 미사용 — PoC 범위 minimal.
- `ActionSpaceState.activeRightTab: 'reasoning' | 'coding'`

### historical thread
- `ThreadDetailResponse.coding_summary.tree / diffs` 가 있으면 `RepoTreePanel`에 hydrate
- 없으면 tree 자리에 "This thread has no captured file tree." 한 줄 placeholder

## 데이터 계약

### 신규 타입 (Phase 0)

```python
# apps/backend/schemas/coding.py
class FileEntry(BaseModel):
    path: str
    kind: Literal["file", "dir"]
    size_bytes: int | None = None
    changed_status: Literal["M", "A", "D", "R", "?"] | None = None

class DiffSnippet(BaseModel):
    path: str
    unified_diff: str   # per-file truncated slice of `git diff --unified=3 --no-color`
    truncated: bool = False

class CodingSummary(BaseModel):
    # 기존 유지 …
    tree: list[FileEntry] = Field(default_factory=list)
    diffs: list[DiffSnippet] = Field(default_factory=list)
```

### `from_turn_metadata` projection 라인 (qa 리뷰 반영)
- `workspace_summary.get("tree", [])` → `[FileEntry(**x) for x in ...]`
- `workspace_summary.get("diffs", [])` → `[DiffSnippet(**x) for x in ...]`
- optional 필드라 기존 레거시 metadata는 빈 리스트로 hydrate.

### TypeScript mirror

```typescript
// apps/frontend/src/types/coding.ts
export interface FileEntry { path: string; kind: 'file' | 'dir'; size_bytes?: number | null; changed_status?: 'M'|'A'|'D'|'R'|'?' | null; }
export interface DiffSnippet { path: string; unified_diff: string; truncated?: boolean; }
// CodingSummary에 optional tree/diffs 추가
```

### 백엔드 상한 상수
- `WORKSPACE_SUMMARY_MAX_BYTES = 128 * 1024`  (`services/repository_workspace_service.py`)
- tree: depth 2, 최대 200 entries, `.git` 제외, 바이너리 제외
- diffs: 최대 20 파일, 파일당 4 KB truncate

---

## Phase 0. 계약 고정

- [ ] `schemas/coding.py` — `FileEntry` / `DiffSnippet` 추가 + `CodingSummary.tree/diffs` optional 필드
- [ ] `CodingSummary.from_turn_metadata` — tree/diffs projection 라인 추가
- [ ] `types/coding.ts` — mirror
- [ ] `sse-contract` 스킬 변경 **없음** (attachments shape 그대로)

검증
- [ ] pydantic 스냅샷: 기존 metadata_json으로 hydrate 시 tree/diffs 빈 리스트 반환
- [ ] tsc --noEmit 통과

## Phase 1. `summarize_workspace` 확장

- [ ] `_summarize_workspace_sync` — 현재 반환 dict에 `tree`, `diffs` 추가
- [ ] **단일 `git diff --unified=3 --no-color` 호출**로 전체 diff 수집 후 파일 단위 파싱(`diff --git a/... b/...` 블록 split)
- [ ] tree 수집: `git ls-files --cached --others --exclude-standard` 1회 + `os.scandir` depth 2 (바이너리·`.git` 제외). 200 entries soft cap
- [ ] diff truncation: 파일당 4 KB 초과 시 뒤를 잘라내고 `truncated=True`
- [ ] 전체 payload `WORKSPACE_SUMMARY_MAX_BYTES=128KB` 초과 시 diffs 순차 drop

검증
- [ ] `tests/test_workspace_manager.py` — tree/diffs 2~3개 케이스 (repo 없음 / 단일 파일 수정 / 바이너리 포함) assert 추가
- [ ] backend 성능 메모: 50-file 레포 기준 `summarize_workspace` 측정 (목표 <150ms)

## Phase 2. 우측 aside 탭 분리

- [ ] `CodingAsideTabs.tsx` (신규) — `Reasoning` / `Coding` 탭 wrapper (role="tablist", aria-controls)
- [ ] `ActionSpaceState.activeRightTab` 추가, 기본값 규칙 (coding signal 여부)
- [ ] `WorkspaceRouteRoot.tsx` — aside 내부를 탭 구조로 교체

검증
- [ ] `src/lib/workspace-state.test.ts` — 기본 탭 선택 규칙 테스트
- [ ] Playwright: 비-coding thread 기본 Reasoning, coding thread 기본 Coding

## Phase 3. RepoTreePanel + 인라인 Diff

- [ ] `RepoTreePanel.tsx` (신규) — `CodingSummary.tree` 입력, depth prefix(`│ ` 등)로 flat 렌더, `changed_status` 있는 row color 강조
- [ ] tree row 클릭 → `<details>`로 같은 컴포넌트 내부에 `<pre>` diff 펼침 (별도 모달 없음)
- [ ] diff line `+` / `-` / ` ` 접두사 색상 (패키지 추가 없이 자체 CSS)
- [ ] `truncated` 표시 시 "… diff truncated (4KB cap)" fallback 라인
- [ ] `CodingChangeSetCard` **삭제**, `WorkspaceRouteRoot.tsx`의 Coding 탭 순서를 `RepoTreePanel → VerificationStatusCard → ExecutionPolicyCard`로 재배치

검증
- [ ] vitest: tree 렌더 + 변경 파일 highlight + row 클릭 시 `<details[open]>` 확인
- [ ] Playwright: S2 thread에서 README 변경 highlight 및 diff 펼침 확인
- [ ] a11y 체크: `role="tablist"`, `aria-expanded` 존재

## Phase 4. Historical hydrate 확인 (검증 only)

- [ ] `get_latest_coding_summary` 코드 변경 없음 (Phase 0의 `from_turn_metadata`로 자동 처리됨)
- [ ] `createActiveThreadStateFromDetail` 코드 변경 없음 (optional 필드 자동 흡수)
- [ ] historical thread에서 tree/diff 없으면 `RepoTreePanel`이 "no captured tree" 한 줄 표시

검증
- [ ] Playwright: 저장된 S2 thread 재방문 시 tree/diff hydrate 확인
- [ ] 이전 버전 metadata(tree 필드 없음)인 thread 접근 시 크래시 없이 폴백

---

## 위험 · 완화

- 큰 레포 tree: depth 2 + 200 개 cap, `.git` 제외 → JSONB 100KB 이하 유지
- 대용량 diff: 파일당 4KB + 파일수 20 cap + payload 128KB soft cap → JSONB TOAST로 안전 저장
- 바이너리 파일 diff: `git diff`가 "Binary files differ" 메시지만 반환 → 그대로 unified_diff에 저장 (UI에서도 "(binary)" 표시)
- 접근성: Phase 2/3에서 탭·details에 aria 속성 명시
- persistence 범위 축소: activeRightTab은 session only (reload 시 기본 규칙 복귀) — PoC 수준

## 검증 방법

### 백엔드
- `cd apps/backend`
- `uv run pytest tests/test_workspace_manager.py -v`
- `uv run pytest tests/test_chat_api_coding_flow.py -v`
- `uv run pytest tests/test_coding_supervisor.py tests/test_coding_tools.py -q`

### 프론트엔드
- `cd apps/frontend`
- `npm run lint`
- `npm run test`
- `npm run build`
- Playwright: S2 시나리오 재실행 후 Coding 탭 내 tree/diff/verification/policy 순서 확인

### 수동 시나리오
- [ ] 비-coding thread: aside 기본 `Reasoning`, Coding 탭 클릭 시 비어있음
- [ ] repo 바인딩 후 첫 turn: aside 기본 `Coding`, tree에 변경 없음, Verification/Policy만
- [ ] 단일 파일 수정 turn: tree에 README `M` 하이라이트, row 클릭 시 diff inline 펼침
- [ ] saved coding thread 재진입: tree + diff 모두 hydrate (또는 미지원이면 fallback 문구)

## 완료 기준

- coding turn 중/후 사용자가 우측 aside Coding 탭 하나로 "변경 파일 · 검증 결과 · 실행 정책"을 모두 확인 가능
- 기존 비-coding UX 변동 없음
- 백엔드 변경 2개 파일 (`schemas/coding.py`, `services/repository_workspace_service.py`), 프런트 신규 컴포넌트 2개(`CodingAsideTabs`, `RepoTreePanel`)
- 새 SSE event 0건, supervisor/prompt-kit 변경 0건

---

## 보류 / 이월 (별도 plan 후보)

- `CODING_AGENT_ATTACHMENT_INLINE_PREVIEW_PLAN.md` — attachments 이벤트에 `preview_kind`/`inline_content` optional 필드 + inline 이미지/텍스트 렌더
- `CODING_AGENT_PLAN_TRACKER_PLAN.md` — supervisor 선언 plan JSON + Plan 카드
- `CODING_AGENT_TERMINAL_STREAM_PLAN.md` — run_repo_command stdout/stderr SSE 실시간 노출
- `CODING_AGENT_MODE_TOGGLE_PLAN.md`, `CODING_AGENT_BRANCH_SESSIONS_PLAN.md`, `CODING_AGENT_SELECTOR_EDITOR_PLAN.md`

## 참조

- 리뷰 리포트:
  - `_workspace/plan_review_frontend.md`
  - `_workspace/plan_review_backend.md`
  - `_workspace/plan_review_qa.md`
- MiniMax Agent: https://www.minimax.io/news/minimax-agent
- MiniMax M2 & Agent: https://www.minimax.io/news/minimax-m2
- Mini-Agent 오픈소스: https://github.com/MiniMax-AI/Mini-Agent
- 2026 AI 코딩 에이전트 UI 트렌드: https://fungies.io/ai-coding-agents-guide-2026/ , https://visualstudiomagazine.com/articles/2026/02/24/in-agentic-ai-its-all-about-the-markdown.aspx
- 내부 선행 계획: `plans/CODING_TEAM_CONTROL_PLANE_AND_UI_PLAN.md`
- SSE 계약: `.claude/skills/sse-contract/SKILL.md`
- 내부 UI 진단: `_workspace/ui_ux_live_rediagnosis.md`, `_workspace/ui_ux_before_after_report.md`
