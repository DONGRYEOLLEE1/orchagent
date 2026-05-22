---
작업명: LLM Routing Rule-Based Residue Cleanup
간단요약: rule-based routing 잔재를 제거하고 프롬프트 기반 첫 분기 정책과 UI/SSE 라우팅 검증을 보강한다.
작성일시: 2026-05-22 16:56 KST
최종 수정일시: 2026-05-22 17:04 KST
---

# LLM Routing Rule-Based Residue Cleanup

## 목표

OrchAgent의 head/team supervisor 라우팅이 정규식, 키워드, 강제 분기 없이 `RouterDecision` 기반 LLM 결정과 허용된 safeguard 4종만으로 동작하도록 정리한다.

## 범위

- `packages/agent-core/src/agent_core/`
- `apps/backend/workflow/`
- `packages/prompt-kit/src/prompt_kit/prompts.py`
- 관련 백엔드 테스트와 Playwright UI 시나리오

## 감사 결과

- [x] `reject_coding_team_without_repo_binding`은 5번째 safeguard라서 제거 대상이다.
- [x] `head_supervisor.py`가 repo binding 유무로 `coding_team` 결정을 `FINISH`로 강제 변경한다.
- [x] `team_supervisor.py`가 dispatch limit 도달 시 LLM 호출 전 직접 `FINISH`로 강제 종료한다.
- [x] `router_schema.py`에 `_should_force_approval` 문서 잔재가 남아 있다.
- [x] 실제 `vision_team` worker는 `vision_analyst` 하나이며, CLAUDE.md 표의 `image_inspector`/`image_editor`와 이름이 다르다.

## Phase 1. Rule-Based Residue Removal

- [x] 5번째 repo-binding safeguard와 호출부 제거
- [x] team supervisor의 pre-LLM dispatch-limit shortcut 제거
- [x] router schema의 `_should_force_approval` 잔재 제거
- [x] 관련 safeguard 테스트 정리

## Phase 2. Prompt And Test Coverage

- [x] head/team/research/data/coding/writing/vision 첫 분기 프롬프트 보완
- [x] 실제 worker 이름과 다른 image worker 정책을 안전하게 정리
- [x] prompt/safeguard/router 테스트 추가 또는 갱신

## Phase 3. Verification

- [x] grep으로 rule-based routing 패턴 확인
- [x] 관련 pytest 통과 확인
- [ ] Playwright MCP로 CSV 첨부, 이미지 첨부, 최신 뉴스, 인사 시나리오 확인
- [ ] SSE `route` 이벤트 reason과 Inner Monologue 패널 확인

차단 사유: 2026-05-22 17:02 KST 기준 Playwright MCP `browser_navigate` 호출이 `user rejected MCP tool call`로 거절되었고, sandbox에서 `localhost:3000`/`localhost:8002` 접근도 `Operation not permitted`로 실패했다. 대체 검증으로 프론트 SSE/Inner Monologue 테스트를 실행했다.

## 검증 기록

- `rg -n "_should_force|_APPROVAL_PATTERNS|re\\.(match|search)|keyword|keywords|reject_coding_team_without_repo_binding|_force_finish_due_to_dispatch_limit" packages/agent-core/src/agent_core apps/backend/workflow packages/prompt-kit/src/prompt_kit` → 0건
- `PYTHONPATH=apps/backend MPLCONFIGDIR=/private/tmp/mpl-cache UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest apps/backend/tests/test_router_safeguards.py apps/backend/tests/test_supervisor.py apps/backend/tests/test_routing_prompts.py apps/backend/tests/test_llm_router.py -q` → 31 passed
- `PYTHONPATH=apps/backend MPLCONFIGDIR=/private/tmp/mpl-cache UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest apps/backend/tests/test_team_subgraphs.py apps/backend/tests/test_planner.py apps/backend/tests/routing_eval/test_scorer.py -q` → 15 passed
- `PYTHONPATH=apps/backend MPLCONFIGDIR=/private/tmp/mpl-cache UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest apps/backend/tests -q` → 190 passed
- `npm run test -- src/lib/sse-reducer.test.ts src/app/page.test.tsx` → 24 passed

## 커밋 상태

- 2026-05-22 17:04 KST 기준 `git add ...` 실행 시 `.git/index.lock` 생성이 `Operation not permitted`로 차단되었다.
- `test -w .git` / `test -w .git/index`도 현재 sandbox에서 writable이 아니라고 반환한다.
- 따라서 변경은 검증 완료 상태지만, 이 세션에서는 커밋 생성이 차단되었다.

## 검증 방법

- `rg -n --glob '*.py' "_should_force|_APPROVAL_PATTERNS|re\\.(match|search)|keyword|keywords" packages/agent-core/src/agent_core apps/backend/workflow packages/prompt-kit/src/prompt_kit`
- `cd apps/backend && uv run pytest tests/test_router_safeguards.py tests/test_llm_router.py tests/test_supervisor.py tests/test_team_subgraphs.py tests/test_planner.py -q`
- 가능한 경우 전체 백엔드 테스트 또는 routing eval 실행
- 가능한 경우 `./infra/scripts/start-dev.sh` 후 Playwright MCP UI 검증
