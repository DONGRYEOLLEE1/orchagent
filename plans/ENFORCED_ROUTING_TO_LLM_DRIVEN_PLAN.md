# 강제 라우팅 → LLM-Driven Routing 전환 계획서

## 작성 일자
2026-05-22

## 목적
백엔드 코드베이스에 남아 있는 모든 **룰베이스 강제 라우팅**(키워드 사전, 휴리스틱 분기, LLM 결정 덮어쓰기 inline)을 식별하고 [CLAUDE.md §"Supervisor → Sub-agent Handoff 정책"](../CLAUDE.md) 및 `plans/CODEBASE_WIDE_REFACTORING_PLAN.md` §4.0 P1–P5 정책에 맞게 제거·전환한다.

- **P1**: 모든 라우팅·handoff는 LLM `RouterDecision` 결정. 코드에서 정규식/키워드/`_should_force_*` 사용 금지.
- **P2**: 의도 가이드는 `packages/prompt-kit`이 단일 출처. 코드에 중복 인코딩 금지.
- **P3**: 안전망은 `agent_core/safeguards.py`의 함수 4종(+ 본 계획에서 1종 추가)만. 차단(FINISH) 또는 재요청(retry)만 허용.
- **P4**: 모든 결정·safeguard 발동은 `route_history` → SSE `route` 이벤트로 가시화.
- **P5**: 라우팅 회귀는 `tests/routing_eval/`의 골든 데이터셋이 정량 측정.

## 발견된 위반·대상 (Explore + 직접 검증)

| # | 분류 | 위치 | 함수/패턴 | 정책 위반 여부 | 조치 |
| :-: | :--- | :--- | :--- | :---: | :--- |
| 1 | **P1 위반** | `packages/agent-core/src/agent_core/nodes/planner.py` L37-86 | `_build_simple_research_plan()` — 키워드 사전(`research_markers`, `answer_markers`, `complex_markers`) 매칭으로 plan 사전 생성 | ❌ 위반 | 함수·호출부 제거, LLM planner의 `with_structured_output(TaskPlan)`만 사용 |
| 2 | **P1 위반·죽은 코드** | `head_supervisor.py` L72-99 | `_orchagent_identity_response()` — 정체성 질의용 키워드 사전 (현재 호출처 0건, supervisor.py re-export만 잔존) | ❌ 위반 잔재 | 함수 + 재내보내기 모두 삭제. `SYSTEM_SUPERVISOR_PROMPT` `# IDENTITY` 블록이 이미 처리. |
| 3 | **P3 inline·미등록** | `head_supervisor.py` L163-171 | LLM이 `coding_team` 선택 + `repo_binding` 없을 때 inline으로 `next_node = "FINISH"` 덮어쓰기 | ⚠ P3 정신 부합하나 등록 누락 | `safeguards.py`에 `reject_coding_team_without_repo_binding()` 함수로 추출, head_supervisor에서 호출 |
| 4 | **죽은 코드** | `planner.py` L17-34 `_extract_latest_user_text`, `head_supervisor.py` L43-69 `_extract_message_text`/`_latest_user_request_text` | `_build_simple_research_plan`/`_orchagent_identity_response`만 사용 → 1·2 제거 시 동반 죽은 코드 | — | 동반 삭제, supervisor.py re-export도 정리 |

### Safeguard로 유지·이동되는 차단 로직 (`coding_team` + `repo_binding`)
- **이유**: 사용자가 repo를 바인딩하지 않은 상태에서 LLM이 `coding_team`을 선택하면 worker가 절대로 동작 불가(필수 선행조건). 이건 의도 분류가 아니라 시스템 무결성 차단이므로 P3 정신(차단/재요청만)에 부합.
- **차이점**: 기존 inline 코드는 SSE `route` 이벤트의 `reason`에 safeguard 표시가 없었음. 추출 후에는 `safeguard: …` 접두어 reason이 가시화되어 [P4 정책]에 맞게 사용자에게 노출.
- **이름 협의**: `reject_coding_team_without_repo_binding(decision, repo_bound: bool)`. `safeguards.py`의 다른 `reject_*`/`enforce_*` 네이밍과 일관.

## Phase 분해

### Phase 1 — planner 휴리스틱 제거 (P1)
**파일**: `packages/agent-core/src/agent_core/nodes/planner.py`

- [x] `_build_simple_research_plan` 함수 삭제 (L37-86)
- [x] `_extract_latest_user_text` 함수 삭제 (L17-34, 더 이상 호출처 없음)
- [x] `planner_node` 본체에서 lightweight plan 분기(L104-117) 삭제 → LLM planner의 `with_structured_output(TaskPlan)` 단일 경로만 남김
- [x] `PLANNER_PROMPT`(`packages/prompt-kit/src/prompt_kit/prompts.py` L190-210) 점검: "lightweight research" 케이스(`예: 웹검색 → 답변`)도 이미 다룰 수 있음(예시 L207-209 `[research_team] Search for latest trends in AI` 포함). 추가 가이드 불필요 — **프롬프트 수정 없음**.

**회귀 위험**: 기존 `test_planner.py::test_planner_uses_lightweight_plan_for_simple_research_query`가 휴리스틱 동작을 잠그고 있음. 이 테스트는 정책 위반이므로 **삭제 후 LLM-driven 검증 테스트로 대체**.

### Phase 2 — `_orchagent_identity_response` 죽은 코드 정리 (P1·P2)
**파일**: `packages/agent-core/src/agent_core/supervisors/head_supervisor.py`, `packages/agent-core/src/agent_core/supervisor.py`

- [x] `head_supervisor.py` L72-99 `_orchagent_identity_response` 함수 삭제
- [x] `head_supervisor.py` L43-69 `_extract_message_text`, `_latest_user_request_text` 동반 삭제 (호출처 0건 확인)
- [x] `head_supervisor.py` L36-40 "Helpers — lifted from the previous monolithic supervisor.py" 코멘트 블록 정리
- [x] `supervisor.py` L28-33 import에서 3개 헬퍼 제거, `__all__`(L70-74)도 정리. 외부 import 가능성을 위해 `make_supervisor_node`/`make_head_supervisor_node`만 남김.

**회귀 위험**: tests/에서 3개 헬퍼 import 검색 → 0건 확인됨(`grep -rn "_extract_message_text\|_latest_user_request_text\|_orchagent_identity_response" apps/backend/tests/` 결과 없음).

### Phase 3 — `coding_team` repo_binding 체크를 safeguards로 추출 (P3·P4)
**파일**: `packages/agent-core/src/agent_core/safeguards.py`, `packages/agent-core/src/agent_core/supervisors/head_supervisor.py`

- [x] `safeguards.py`에 함수 추가:

  ```python
  def reject_coding_team_without_repo_binding(
      decision: RouterDecision,
      *,
      repo_bound: bool,
  ) -> SafeguardOutcome:
      """Force FINISH if LLM picks coding_team without a bound repository.

      Coding workers require a bound repository to read/write files. When the
      LLM selects coding_team without one we cannot proceed — block and force
      FINISH so the head supervisor returns a direct answer instead.
      """
      if decision.next != "coding_team" or repo_bound:
          return SafeguardOutcome(decision=decision)
      return SafeguardOutcome(
          decision=RouterDecision(
              next="FINISH",
              reason="safeguard: coding_team requires a bound repository.",
              request_review=False,
              team_finished=True,
          ),
          status="fallback_finish",
      )
  ```

- [x] `__all__`에 `reject_coding_team_without_repo_binding` 추가.
- [x] `head_supervisor.py` L163-171 inline 차단 로직을 `reject_coding_team_without_repo_binding` 호출로 교체. safeguard outcome의 `status != "accepted"`이면 reason을 `route_history`에 반영(SSE `route` 이벤트에 `safeguard: …` 노출).
- [x] 호출 시점: `decide_route()`가 반환한 `decision`을 받은 직후, `_maybe_interrupt` 이전(현재 inline 위치와 동일).

### Phase 4 — 회귀 잠금 테스트 (Core §2 contract · §3 safeguard)
**CLAUDE.md 테스트 정책 준수**: Core 카테고리 §3 (safeguard) + §2 (contract) 보장. 신규 파일이 아닌 **기존 테스트 파일**에 케이스 추가 우선.

- [x] `apps/backend/tests/test_router_safeguards.py`에 2건 추가:
  - `test_coding_team_without_repo_binding_forces_finish`
  - `test_coding_team_with_repo_binding_passes_through`
- [x] `apps/backend/tests/test_planner.py` 회귀 정책 위반 테스트 교체:
  - 삭제: `test_planner_uses_lightweight_plan_for_simple_research_query` (휴리스틱 동작 잠그던 케이스)
  - 추가: `test_planner_always_invokes_llm` (`FailingPlannerLLM` 자리에 `RecordingPlannerLLM`을 두고 모든 쿼리에서 LLM이 호출됨을 검증)

### Phase 5 — 검증 + 커밋 + 푸시
- [x] `cd apps/backend && pytest tests -q` → 기존 185 PASS 이상 유지 (새 케이스 포함)
- [x] 회귀 측정: `pytest tests/routing_eval/test_scorer.py -q` 통과
- [x] Lint: `grep -rEn "_should_force_|_APPROVAL_PATTERNS|_build_simple_research_plan|_orchagent_identity_response" packages/agent-core` 결과 **0건** 확인
- [x] 명시적 file-level `git add` (작업 무관 unstaged 변경 배제)
- [x] 커밋 메시지: `refactor(routing): remove rule-based heuristics, register repo_binding safeguard`
- [x] `git push -u origin refactor/llm-driven-routing-cleanup`

## 변경 파일 목록

| 파일 | 변경 유형 | LOC 추정 |
| :--- | :--- | :--- |
| `plans/ENFORCED_ROUTING_TO_LLM_DRIVEN_PLAN.md` | 신규 | +130 |
| `packages/agent-core/src/agent_core/nodes/planner.py` | 수정 (-70) | 153 → ~85 |
| `packages/agent-core/src/agent_core/supervisors/head_supervisor.py` | 수정 (-65) | 374 → ~310 |
| `packages/agent-core/src/agent_core/supervisor.py` | 수정 (-10) | 76 → ~55 |
| `packages/agent-core/src/agent_core/safeguards.py` | 수정 (+25) | 147 → ~175 |
| `apps/backend/tests/test_planner.py` | 수정 (재작성) | 83 → ~50 |
| `apps/backend/tests/test_router_safeguards.py` | 수정 (+25) | 113 → ~140 |

총 **5개 코드 파일 + 2개 테스트 파일 + 1개 계획서**.

## 비고
- 모든 변경은 **prompt-driven** 흐름을 유지. 코드에 정규식·키워드 사전·`_should_force_*` 함수는 새로 추가하지 않음.
- `coding-no-repo` 골든 케이스(`golden_dataset.json` `coding-002-no-repo`, `expected_next=FINISH`)가 추출된 safeguard와 의미 일치 → 회귀 차단 보장.
- `_orchagent_identity_response` 삭제는 OpenAI U3 정체성 회귀 시나리오에 영향 없음(SYSTEM_SUPERVISOR_PROMPT `# IDENTITY` 블록이 직접 처리).
