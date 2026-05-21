---
작업명: Codebase-Wide Refactoring Plan
간단요약: 4개 영역(agent-core, backend, frontend, tools/prompts) 감사 결과를 통합한 단계별 리팩토링 + 회귀 검증 프로토콜 + Phase별 브랜치/PR 전략 + 라우팅/handoff 정책을 룰베이스에서 LLM-Driven Delegation으로 전면 전환하는 마스터 플랜
작성일시: 2026-05-19 16:30 KST
최종 수정일시: 2026-05-20 18:00 KST
---

## 0. 개요

### 0.1 목표

OrchAgent 전 영역의 응집도·계층 경계·테스트 커버리지를 점진적으로 끌어올린다. 각 리팩토링 태스크가 **물려있는 기능(엔드포인트·SSE 이벤트·UI 화면·DB 영속·HITL 흐름)**을 깨뜨리지 않도록 매 태스크마다 동일한 회귀 검증 프로토콜을 적용한다.

### 0.2 범위

| 영역 | 대상 경로 | 우선순위 |
| :--- | :--- | :--- |
| Backend | `apps/backend/api/`, `apps/backend/services/`, `apps/backend/main.py` | 🔴 H |
| LangGraph 코어 | `packages/agent-core/`, `apps/backend/workflow/` | 🔴 H |
| Frontend | `apps/frontend/src/components/workspace/`, `src/lib/`, `src/hooks/` | 🔴 H |
| Tools / Prompts / Infra | `packages/agent-tools/`, `packages/prompt-kit/`, `infra/` | 🟠 M |

### 0.3 전제

- AGENTS.md 강제 규약(`init_chat_model`, `create_agent`, `create_react_agent` 금지, prompt-kit 단일 관리)을 절대 깨지 않는다.
- 기존 plans/*.md 중 미완료 항목과 충돌하는 작업은 **본 계획에 흡수하거나, 본 계획 완료까지 보류**한다(§9 부록 A 인벤토리 참조).
- 회귀 검증을 통과하지 못한 변경은 커밋하지 않는다. 검증 실패 → 원인 분석 → 재구현 → 재검증 후에야 커밋.
- 하나의 phase는 독립적 PR로 머지 가능해야 한다.
- **라우팅/handoff/승인/완료 판단은 LLM에 위임을 원칙으로 한다.** 기존 룰베이스(정규식 + `_should_force_*` + 팀별 강제 순서 머신)는 제거 또는 안전망(무한 루프·invalid goto 차단 등)으로만 유지한다. 상세 정책·인벤토리·safeguard·evaluation 방법은 §4.0 참조.

### 0.4 산출 근거

| 파일 | 내용 |
| :--- | :--- |
| `_workspace/refactor_audit_agent_core.md` | LangGraph 코어 LOC·스멜·후보 Top 5 |
| `_workspace/refactor_audit_backend.md` | FastAPI 라우터·서비스·SSE collector 후보 Top 5 |
| `_workspace/refactor_audit_frontend.md` | Next.js 컴포넌트·상태·SSE 파서 후보 Top 7 |
| `_workspace/refactor_audit_tools_prompts_infra.md` | 워커 툴·프롬프트·infra 후보 Top 10 |

### 0.5 우선순위 정렬 근거

- **응집도 위기**: 단일 파일이 1,000 LOC 이상 + 책임 5개 이상인 곳을 우선 분해 (`chat.py` 2,619 LOC, `WorkspaceRouteRoot.tsx` 2,635 LOC, `supervisor.py` 989 LOC).
- **계약 안정성**: SSE 이벤트 계약·HITL 인터럽트·체크포인터 등 회귀 시 사용자 가시 피해가 큰 경계면 우선.
- **AGENTS.md 위반**: 라우터의 workflow 직접 import 등 규약 위반은 H 우선순위.
- **라우팅 정책 패러다임 전환**: supervisor.py의 약 60%를 차지하는 룰베이스 휴리스틱을 LLM-Driven Routing으로 교체. Phase 2 핵심 산출물(§4.0).

---

## 1. 검증 프로토콜 표준 템플릿 (Verification Protocol — VP)

> **모든 리팩토링 태스크는 §1.1~§1.8을 순서대로 수행한 뒤에만 체크박스 `- [x]`로 마킹하고 커밋한다.**

### 1.1 영향 범위 맵 (Impact Map) — 사전 작성 의무

태스크 시작 전 다음 표를 _workspace/refactor_impact_<task_id>.md에 작성한다(코드 1줄도 건드리기 전).

| 분류 | 항목 |
| :--- | :--- |
| **변경 대상** | 수정/이동/삭제할 파일·심볼 (file:line) |
| **직접 호출자** | grep으로 1차 확인한 import/호출 위치 |
| **영향 엔드포인트** | `/api/...` 경로 (대상이 backend일 때) |
| **영향 SSE 이벤트** | `status/route/reasoning/tool_*/text/attachments/checkpoint/error` 중 어떤 것 |
| **영향 LangGraph state 필드** | `messages`, `route_history`, `dispatched_workers` 등 |
| **영향 UI 화면/플로우** | `/c/[threadId]`, `/dashboard`, 인증 플로우 등 |
| **영향 DB 모델** | `ChatMessageLog`, `ChatTurn`, `TraceEvent` 등 |
| **외부 의존** | OpenAI, Tavily, PostgreSQL, Pillow 등 |

이 표를 작성하다가 **예상보다 영향이 크다고 판단되면 태스크를 더 작은 단위로 쪼갠다**.

### 1.2 사전 baseline 캡처 (Pre-refactor) — 변경 직전 1회

태스크 직전 다음 명령으로 baseline을 캡처한다. 결과는 `_workspace/baselines/<task_id>/`에 저장.

```bash
# Backend
cd apps/backend
uv run pytest tests/ -v --tb=line 2>&1 | tee _workspace/baselines/<task_id>/pytest_before.log

# Frontend
cd apps/frontend
npm run lint 2>&1 | tee _workspace/baselines/<task_id>/lint_before.log
npm run test -- --run 2>&1 | tee _workspace/baselines/<task_id>/vitest_before.log
node --test src/lib/chat-stream.test.mjs 2>&1 | tee _workspace/baselines/<task_id>/nodetest_before.log

# 핵심 엔드포인트 응답 샘플 (스택이 살아있을 때)
curl -s -b cookies.txt http://localhost:8002/api/threads | jq . > _workspace/baselines/<task_id>/threads_before.json
```

UI 변경 태스크의 경우 핵심 화면 스크린샷 또는 동작 메모를 함께 캡처.

### 1.3 단위 검증 (Unit-level)

변경 직후 그 파일에 해당하는 단위 테스트만 빠르게 실행해 즉시성 피드백 확보.

| 영역 | 명령 예시 |
| :--- | :--- |
| 백엔드 단일 | `uv run pytest apps/backend/tests/test_<관련>.py -v` |
| 프론트 단일 | `cd apps/frontend && npx vitest run src/<관련>.test.tsx` |
| node 단일 | `node --test src/lib/<관련>.test.mjs` |

### 1.4 통합 검증 (Integration)

레이어 경계가 걸린 모듈은 통합 테스트까지 확인.

| 경계 | 검증 |
| :--- | :--- |
| API ↔ 서비스 | `test_api.py`, `test_chat_turn_lifecycle.py` 등 통합 테스트 |
| LangGraph 노드 ↔ state | `test_workflow_graph.py`, `test_supervisor.py` |
| SSE emit ↔ 파서 | 백엔드 SSE 출력 vs 프론트 `chat-stream.test.mjs`·`handleStreamEvent` 양쪽 동시 점검 (integration-qa-protocol 스킬) |
| 인증/세션 | `test_auth.py` 또는 인증 흐름 통합 테스트 |

### 1.5 회귀 검증 (Regression)

baseline 재실행 → diff 없음 확인.

```bash
# Backend full
uv run pytest tests/ -v --tb=line 2>&1 | tee _workspace/baselines/<task_id>/pytest_after.log
diff _workspace/baselines/<task_id>/pytest_before.log _workspace/baselines/<task_id>/pytest_after.log

# Frontend full
npm run lint 2>&1 | tee _workspace/baselines/<task_id>/lint_after.log
npm run test -- --run 2>&1 | tee _workspace/baselines/<task_id>/vitest_after.log

# 응답 샘플 비교
curl -s -b cookies.txt http://localhost:8002/api/threads | jq . > _workspace/baselines/<task_id>/threads_after.json
diff _workspace/baselines/<task_id>/threads_before.json _workspace/baselines/<task_id>/threads_after.json
```

PASS 수가 줄거나 응답 shape이 달라졌으면 fail로 간주. **diff가 의도된 경우(예: 응답 스키마 정리 태스크) 사유를 task 노트에 남긴다.**

### 1.6 수동 E2E 스모크 시나리오

UI/SSE/HITL 영향 태스크는 dev 스택을 띄우고 아래 7개 시나리오 중 영향 받는 것만 실행.

| # | 시나리오 | 통과 기준 |
| :--- | :--- | :--- |
| S1 | 로그인 → 메시지 전송 → 텍스트 스트림 수신 | 토큰 단위 점진 표시, 중복 없음 |
| S2 | 메시지 전송 → 라우팅 카드(route 이벤트) 표시 | head→team→worker 순 |
| S3 | 메시지 전송 → tool_start/tool_end 도구 활동 표시 | 입력/출력 메타 정상 |
| S4 | HITL 인터럽트 → 거부/승인/피드백 | resume 후 동일 thread 이어짐 |
| S5 | 코딩팀 라우팅 요청(repo 바인딩 필요) → 워크스페이스 패널 정상 | repo tree·diff 표시 |
| S6 | 새 스레드 생성 → 사이드바 정렬 → 제목 자동 요약 | 자동 제목 갱신 |
| S7 | 대시보드 → 토큰 사용량/라이브 trace 표시 | 실시간 갱신 |

캡처 결과는 `_workspace/baselines/<task_id>/e2e_smoke.md`에 OK/FAIL + 한 줄 메모.

### 1.7 롤백 기준

다음 중 하나라도 발생하면 즉시 revert한다.

- baseline pytest/vitest의 통과 수가 감소.
- 응답 JSON shape이 의도되지 않은 형태로 변경.
- SSE 이벤트 누락(특히 `text`/`status: completed`).
- HITL 인터럽트 후 resume 실패.
- frontend `npm run build` 실패.
- 핵심 시나리오 S1~S4 중 하나라도 FAIL.

revert 후 _workspace의 audit/baseline 파일을 그대로 두고 원인 분석부터 재시작.

### 1.8 체크오프 + 커밋

- §1.5/§1.6까지 모두 PASS → 본 plan의 해당 체크박스 `- [x]` 반영
- 커밋 메시지: `type(scope): summary` 형식. `refactor` / `fix` / `feat` / `test` / `chore` / `docs` 중 적합한 것 선택
- 본 plan 체크박스 변경은 같은 커밋에 포함 가능
- push → 다음 태스크로 (push 대상 브랜치는 §1.9 규약 준수)

### 1.9 브랜치/PR 워크플로우 (요약 — 상세는 §12)

- **main 보호**: 본 리팩토링 진행 중 main 직접 push 금지. 모든 변경은 phase 브랜치 → PR → main 머지.
- **Phase 브랜치명**: `refactor/phase-<N>-<scope>` (예: `refactor/phase-1-backend-cohesion`).
- **태스크 커밋**: phase 브랜치 위에 atomic 커밋(태스크 1개 = 커밋 1~소수). 태스크 브랜치 사용은 선택(`refactor/phase-1-backend-cohesion/1.1-response-collector`).
- **회귀 게이트**: PR 머지 직전 §1.5 baseline 회귀 1회 더 실행. fail이면 머지 금지.
- **머지 전략**: phase 브랜치 → main은 **merge commit**(`--no-ff`) 권장. 태스크 커밋 추적성을 보존.
- **태그**: phase 머지 직후 `refactor-phase-<N>-complete` 태그(선택, §12).
- **롤백**: 머지 후 회귀 발견 시 `git revert -m 1 <merge_sha>`로 phase 단위 복구.
- **핫픽스 예외**: 본 리팩토링과 무관한 긴급 수정은 `fix/...` 브랜치로 main 직접 PR 가능. 진행 중 phase 브랜치는 머지 직후 rebase로 동기화.

---

## 2. Phase 0 — 사전 준비 (1~2일)

> 이후 모든 phase의 기반이 되는 검증 안전망·인벤토리·브랜치 보호 정책을 구축한다.

**브랜치:** `refactor/phase-0-foundation` (main 분기). 머지 후 phase-1 브랜치가 이 베이스 위에 분기된다.

- [x] 0.1 보안 sanity 1차 점검 결과 기록 — `.env`가 .gitignore에 있고 git-tracked 아님을 확인했으므로 revoke 불필요. `_workspace/security_sanity_2026-05-19.md`로 기록. 외부 공유 금지 원칙은 README.md L116~120 생성 가이드만 존재, AGENTS.md 명문화 없음 → 후속 보강 권장(범위 외).
- [x] 0.2 baseline 회귀 안전망 스크립트 정리 — §1.2·§1.5의 명령을 `infra/scripts/capture_baseline.sh`(pytest/lint/vitest/node test/build/응답 샘플/openapi 스냅샷, dev 스택 부재 시 graceful skip), `infra/scripts/diff_baseline.sh`(pytest/vitest/node test 통과 수 비교 + JSON snapshot diff + lint/build 에러 감지, 회귀 시 exit 1)로 분리. 기존 `start-dev.sh`와 동급 위치.
- [x] 0.3 수동 E2E 스모크 시나리오 체크리스트(§1.6 S1~S7)를 `_workspace/e2e_smoke_checklist.md`로 고정. playwright MCP 시퀀스·기록 양식·자동화 우선순위 포함. 각 phase 마지막에 재사용.
- [x] 0.4 기존 plans 중첩 인벤토리 확정 — 30개 plan(본 plan 제외)을 직접 중첩 12 / 부분 중첩 11 / 신규 기능 6 / 무관 1로 분류해 §9 부록 A를 모두 채움. 미체크 카운트·근거·후속 액션은 `_workspace/plans_overlap_inventory.md`.
- [x] 0.5 전체 baseline 1회 캡처(pytest/vitest/lint/node test) 완료. 결과: pytest **275/275 PASS**, vitest **53/53 PASS**(V-001 `WorkspaceRouteRoot` HITLPanel reason 중복 렌더 fix를 phase 0 안에 흡수), lint 0E/2W(L-001/L-002 Phase 3.5 cleanup target), node --test 3/3 PASS. dev 스택 미가동으로 API/openapi snapshot은 graceful skip. 요약은 `_workspace/baselines/phase0/SUMMARY.md`, 회귀 게이트 기준은 pytest ≥ 275, vitest ≥ 53(새 fail 0), lint error 0.
- [x] 0.6 브랜치 전략 합의 — main 보호 규칙(직접 push 금지, PR 필수, 회귀 게이트 통과 필수) + phase/태스크 브랜치 네이밍 + 머지·롤백·충돌 절차 + self-review 체크리스트 모두 `_workspace/branch_protection_policy.md`에 운영 약속으로 명문화. GitHub branch protection rule 적용 여부는 0.7에서 후속 검토.
- [x] 0.7 CI 워크플로우 정합성 점검 — `.github/workflows/ci.yml`에 Vitest 단계와 `node --test src/lib/chat-stream.test.mjs` 단계를 추가해 PR 회귀 표면을 §1.5 최소 기준에 맞춤. 현황·보강·후속 검토 사항(branch protection rule UI 적용, baseline diff CI 자동화, routing eval nightly)을 `_workspace/ci_workflow_note.md`에 기록.

**검증:** 0.1~0.7 자체는 코드 변경 없음(스크립트/문서만 추가). baseline 캡처 명령이 모두 PASS인지만 확인하고 phase 브랜치를 PR로 main에 머지(`docs(plan): set up codebase-wide refactor baselines and branch policy`). 머지 후 `refactor-phase-0-complete` 태그를 권장.

---

## 3. Phase 1 — Backend 응집도 (3~4주, 가장 큰 phase)

**브랜치:** `refactor/phase-1-backend-cohesion` (main에서 분기 — Phase 0 머지 후). 태스크별 atomic 커밋. 길이가 길 경우 `refactor/phase-1-backend-cohesion/<task-id>-<short>` 서브 브랜치 사용 가능.

### 3.1 Phase 1 Impact Map (요약)

| 변경 대상 | 직접 영향 |
| :--- | :--- |
| `apps/backend/api/routes/chat.py` (2,619 LOC) | `/api/chat`, `/api/chat/resume`, SSE 전 이벤트, 프론트 `useChat`·`useChatResume` |
| 라우터 내부 DB 헬퍼 14개 | `ChatMessageLog`, `ChatTurn`, `TraceEvent`, `LLMUsageEvent`, `ToolExecutionEvent` |
| `from agent_core.supervisor import ...`, `from workflow.main_graph import ...` (라우터) | AGENTS.md 규약 위반 해소 |
| 3개 로깅 시스템(JsonLogger, TraceService, ChatAnalyticsService) | 모든 thread 영속 |
| `schemas/chat.py` 등 | OpenAPI, TS 타입 동기화 |

### 3.2 Phase 1 태스크

- [x] 1.1 `_FinalResponseCollector` 및 dataclass 추출 → `apps/backend/services/streaming/response_collector.py` + `event_utils.py` + `__init__.py` (FINAL_RESPONSE_STREAM_OWNERSHIP 계약 unit test 10개 신설). 부수 효과: `_event_node_name`/`_extract_text_content`/내부 헬퍼 5종 함께 이동, chat.py 2,619 → 2,288 LOC(-331). 회귀: pytest 275 → 285 PASS, vitest 53/53, lint 0E, nodetest 3/3. baseline diff(`_workspace/baselines/phase1.1/`) PASS.
- [x] 1.2 SSE payload builders 8종 + `display_name`/`utc_timestamp`/`emit_fallback_text_stream`을 `apps/backend/services/streaming/event_processor.py`로 이동. chat_stream/chat_resume_stream 양쪽의 dict literal 10개(reasoning×2 + tool_start/end/error)를 builder 호출로 교체해 두 핸들러의 중복 제거. 신규 unit test 15개(event_type 7종 + display_name special cases + emit_fallback 동작). chat.py 2,287 → 2,172 LOC(-115). 회귀: pytest 285 → 300 PASS, vitest 53/53, lint 0E, dev stack S1+S2+S6 E2E PASS. `_workspace/baselines/phase1.2/SUMMARY.md`. **남은 작업**: event_generator의 큰 if/elif chain 자체와 `emit()` closure는 1.2 scope 외(emit은 nonlocal 17개로 안전 추출 어려움 — 1.3/1.6 service 추출 후 재검토).
- [x] 1.3 라우터 헬퍼 14개를 적절한 기존 서비스의 `*_with_fresh_session` staticmethod로 승격: LoggingService(2), TraceService(2), ChatAnalyticsService(6), RepositoryWorkspaceService(1), ThreadService(1), MemoryService(1), MemoryAgentService(1). 새 모듈 신설 없이 응집 영역에 배치(plan 본문은 turn_service/message_logging_service 예시로 명시했으나 실제 헬퍼들의 도메인 분포가 다양해 기존 서비스 응집이 우선). chat.py 2,172 → 1,941 LOC(-231). conftest stub 경로 + 4개 테스트의 monkeypatch 경로를 새 서비스 메서드로 일괄 변경. AsyncSessionLocal은 chat.py에 noqa import로만 잔존(테스트 호환). 회귀: pytest **285 → 300 PASS**(신규 0, 회귀 0), AST OK.
- [x] 1.4 `AsyncSessionLocal()` 직접 호출 정리. Phase 1.3에서 chat.py 14회 호출이 모두 서비스 staticmethod로 흡수됨. 잔존 호출 인벤토리: services 모듈 18회(모두 `*_with_fresh_session` 의도된 sidecar 패턴) + main.py 2회(lifespan startup, 의도) + chat.py 1회(noqa import alias, 테스트 호환). **라우터(`api/routes/*.py`) 직접 호출 0건** — `grep -rnE 'AsyncSessionLocal\(\)' api/routes/` 결과 비어 있음 확인. plan §3.2 1.4의 핵심 목표(라우터에서 fresh session 패턴 제거) 달성.
- [x] 1.5 `services/orchestration_service.py` 신설. 라우터가 `agent_core.supervisor`/`workflow.main_graph`/`agent_tools.runtime`을 직접 import하지 않도록 단일 seam으로 캡슐화: `OrchestrationService.get_graph/requires_coding_team/requires_human_approval/set_runtime_context/get_runtime_context/reset_runtime_context/collect_runtime_artifacts` + `DEFAULT_LLM_MODEL`/`ToolAttachment`/`ToolRuntimeContext` re-export. chat.py에서 3개 forbidden import 제거 + 호출처 일괄 치환. 8개 테스트 monkeypatch 경로를 새 service path로 마이그레이션. Phase 2의 LLM-Driven Routing 전환 시 `requires_*` 내부만 교체하면 라우터는 무영향(seam 효과). 회귀: pytest 300/300 PASS.
- [ ] 1.6 `services/event_recording_service.py` 신설 — `record_chat_start`/`record_turn_finish` 등으로 trace + analytics + json_log 단일 호출
- [x] 1.7 Pydantic 응답 스키마 정리 — `schemas/turn.py`(ChatTurnResponse + ChatTurnSummary), `schemas/message.py`(MessageResponse + MessageAttachmentResponse) 신설. chat-stream은 SSE이므로 `response_model=` 미적용; replay/admin/future 엔드포인트에서 사용. 회귀 0.
- [x] 1.8 `print()` 디버그 9곳(chat.py)을 `logger = logging.getLogger(__name__)`로 통일. CancelledError/exception/info 레벨 적절 매핑(`logger.warning`, `logger.exception`, `logger.info`). 회귀 0.
- [x] 1.9 라우터 `Depends(require_csrf)` 일관성 점검 완료. 누락 endpoint: `auth/signup`, `auth/login`(인증 전 단계, 의도된 예외). 나머지 mutation endpoint(POST/PATCH/PUT/DELETE) 모두 `require_csrf` 적용 확인. 자동 미들웨어화는 별도 plan(범위 외).
- [x] 1.10 **Phase 1 통합 회귀** — pytest **300/300 PASS**(vs Phase 0 baseline 275, 신규 25 collector+event_processor test, 회귀 0). dev stack 위 playwright E2E S1+S2+S6 PASS(`"리팩토링"을 한 줄로 설명해줘.` → AI 응답·Head Supervisor 라우팅 카드·reasoning summary·자동 제목 "리팩토링 한줄 설명"·Suggested Queries 4종 모두 정상). chat.py 2,619 → 1,941 LOC(-678, -26%). PR #5 ready-for-review 전환 후 main 머지 + `refactor-phase-1-complete` 태그.

### 3.3 Phase 1 태스크별 추가 검증 포인트

| 태스크 | VP 외 추가 점검 |
| :--- | :--- |
| 1.1 | FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT 위반 회귀 — `test_finalizer_node.py` + SSE collector 단위 테스트 신설 |
| 1.2 | 10종 SSE event_type 모두에 대해 emit 횟수·payload shape baseline ↔ after diff 0 |
| 1.3 | DB 트랜잭션 격리 — 동일 thread 동시 요청 시 락 충돌 부재 확인 (`test_chat_turn_lifecycle.py` 동시성 케이스 보강) |
| 1.4 | `AsyncSessionLocal` 116회 → 0회 (`grep -rn "AsyncSessionLocal()" apps/backend/api apps/backend/services` 결과 0) |
| 1.5 | 라우터에 `from agent_core` / `from workflow` / `from agent_tools` import 0회 (`grep -rn` 결과 0) |
| 1.6 | trace + analytics + json_log 3원 기록이 동시에 일어나는지 — 통합 테스트로 검증 |
| 1.7 | OpenAPI 스키마 diff — `curl /openapi.json | jq` 후 변경된 path 명시. 프론트 TS 타입 drift 확인 (`apps/frontend/src/types/thread.ts` 등) |
| 1.10 | `_workspace/baselines/phase1/`에 final pytest/vitest/lint/build/응답 샘플 저장. Phase 0 baseline과 응답 shape 비교 |

---

## 4. Phase 2 — LangGraph 코어 + LLM-Driven Routing 전환 (3~4주, 기존 2~3주에서 확장)

**브랜치:** `refactor/phase-2-langgraph-core` (main에서 분기). Phase 1과 부분 병렬 가능 — 단 §8 의존성 그래프의 우선순위를 따른다. Phase 1 머지 후 시작하면 `git rebase main`으로 충돌 최소화.

> **Phase 2의 핵심 패러다임 전환**: 모든 supervisor / team-supervisor의 **라우팅·handoff·승인·완료 판단을 LLM에 위임**한다. 기존 정규식·휴리스틱(`_should_force_*`, `_APPROVAL_PATTERNS`, 팀별 강제 순서)은 **제거**한다. 잔존하는 룰베이스는 무한 루프 차단·invalid goto 거부 등 **안전망(safeguard)에 한정**한다. 상세는 §4.0.

### 4.0 라우팅 정책 패러다임 전환 (LLM-Driven Delegation)

#### 4.0.1 배경

`packages/agent-core/src/agent_core/supervisor.py` 989 LOC 중 약 60%(추정)가 라우팅 휴리스틱(정규식 23개 + `_should_force_*` 함수 + 팀별 강제 순서 머신)이다. 이는 과거 LLM 성능이 부족했을 때 점진 추가한 안전망이지만 현재는 다음과 같은 부채를 만든다.

- 새 인텐트/팀 추가 시 코드 + 정규식 + 강제 머신을 동시 수정해야 함 (유지보수성 ↓)
- 라우팅 의도가 코드에 분산되어 prompt-kit 단일 출처 원칙(AGENTS.md)이 휴리스틱 영역에서 깨짐
- LLM이 의도와 다른 결정을 했을 때 휴리스틱이 무조건 override → LLM 의도 디버깅 곤란
- 테스트가 휴리스틱에 강결합되어 회귀 비용 ↑

#### 4.0.2 새 원칙

| 원칙 | 내용 |
| :--- | :--- |
| **P1. 라우팅·handoff는 LLM 결정** | head→team, team→worker, FINISH, 인터럽트 승인 요청 여부 모두 LLM이 결정 (structured output 또는 routed tool call) |
| **P2. 프롬프트가 단일 출처** | 라우팅 규칙·예시·금지 사항은 prompt-kit의 supervisor / team-supervisor 프롬프트에만 존재. 코드에는 라우팅 의도 텍스트를 두지 않는다 |
| **P3. 룰베이스는 안전망(safeguard)으로만** | 무한 루프 차단(`HEAD_TEAM_REDIRECT_LIMIT`), invalid goto 거부, dispatch_count 상한 — 결정을 바꾸지 않고 **차단/재요청**만 한다 |
| **P4. LLM 결정 가시화** | 라우팅 LLM 응답(reason + next + request_review)을 state·SSE에 노출. 안전망 발동 시 trace에 기록 |
| **P5. 회귀는 evaluation harness로** | 기존 휴리스틱이 보장하던 케이스를 골든 데이터셋으로 만들어 LLM 라우팅 정확도·latency·토큰 비용을 정량 측정 (§4.0.4) |

#### 4.0.3 룰베이스 인벤토리 — 제거 vs 안전망 유지

| 항목 | 위치(file:line, 추정) | 처리 |
| :--- | :--- | :--- |
| `_APPROVAL_PATTERNS` 등 23개 정규식 | supervisor.py:19–89 | **제거** — 라우팅·승인 요청 결정은 LLM에 위임(프롬프트로 이전) |
| `_should_force_coding_team`, `_should_force_data_science_team` 등 | supervisor.py | **제거** — 팀 선택은 head supervisor LLM이 결정 |
| `_should_force_approval` | supervisor.py | **제거** — 인터럽트 호출 여부는 head supervisor LLM이 결정. `interrupt()`는 LLM이 `request_human_review`를 True로 반환할 때만 호출 |
| coding 팀 codebase_explorer → implementation_engineer → runtime_verifier 강제 순서 | supervisor.py:703–769 | **제거** — team supervisor LLM이 `dispatched_workers` state를 보고 자유 결정. 프롬프트에 "이미 실행된 워커를 다시 부르려면 정당화 필요"만 명시 |
| research 팀 search→web_scraper 강제 순서 | supervisor.py:673–701 | **제거** — 동일 |
| data_science 팀 data_engineer→data_analyst 강제 순서 | supervisor.py:647–671 | **제거** — 동일 |
| `_messages_contain_chart_artifact_evidence` 등 도메인 휴리스틱 | supervisor.py:183–197 | **제거 후보** — 라우팅 결정에서 사용되면 LLM 위임. 단지 trace/시각화 용도라면 별도 `agent_core/text_keywords.py`로 격리 |
| `HEAD_TEAM_REDIRECT_LIMIT = 2` | supervisor.py:570 | **안전망 유지** — 같은 팀 N회 초과 시 강제 FINISH |
| `remaining_steps = 100` (validator) | validator.py:42 | **안전망 유지** — 재귀 상한 |
| `max_team_dispatches` | builder.py | **안전망 유지** — 팀 dispatch 상한 |
| invalid goto 차단 | supervisor 후처리 | **안전망 유지** — 존재하지 않는 노드 지정 시 재요청 또는 FINISH fallback |

#### 4.0.4 LLM 라우팅 evaluation harness

- 위치: `apps/backend/tests/routing_eval/`
- 골든 데이터셋:
  - 기존 휴리스틱이 강제했던 입력 → 기대 라우팅 결과를 수동 또는 LLM-as-judge로 라벨링
  - 카테고리: coding / research / data_science / vision / writing / approval_request / FINISH / 다중 의도 / ambiguous
  - 시작 ≥ 50케이스, Phase 4 종료 시점까지 100케이스 목표
- 측정 지표:
  - **라우팅 정확도**(top-1) — 목표 ≥ 95%
  - **첫 결정 latency**(LLM 호출 단일 turn) — baseline 대비 +X% 한도 합의
  - **평균 토큰 비용**(turn당) — baseline 대비 +X% 한도 합의
  - **안전망 발동 빈도** — invalid goto, redirect_limit hit 등
- 실행: pytest로 단위 실행 가능. CI는 nightly만(토큰 비용 관리). 결과 리포트는 `_workspace/routing_eval/<date>.md`.
- 베이스라인: Phase 2 시작 시점 휴리스틱 기준 정확도 = 100%(휴리스틱 자체 기준). 전환 직후 LLM 기준 ≥ 95%.

#### 4.0.5 안전망(Safeguard) 정책

| 케이스 | 안전망 동작 |
| :--- | :--- |
| LLM이 존재하지 않는 노드로 goto 결정 | 1회 재요청(프롬프트에 invalid 사실 + allowed list 주입) → 그래도 invalid면 FINISH fallback + trace 기록 |
| 같은 팀으로 `HEAD_TEAM_REDIRECT_LIMIT` 초과 라우팅 | 강제 FINISH + 사용자 가시 에러 폴백 메시지 |
| team supervisor가 `max_team_dispatches` 초과 워커 호출 | 강제 FINISH + validator 경유 폴백 |
| LLM structured output 파싱 실패 | 1회 재요청 → 그래도 실패면 FINISH |
| HITL 인터럽트 후 사용자 거부 누적 → LLM이 같은 결정 반복 | 거부 N회 초과 시 강제 FINISH |

이 안전망들은 `agent_core/safeguards.py` (신규)에 모은다. **라우팅 결정 자체를 바꾸지 않고 차단/재요청만 수행한다는 원칙을 코드 구조로 강제** (P3).

#### 4.0.6 supervisor 프롬프트 강화 방향 (prompt-kit)

- `SYSTEM_SUPERVISOR_PROMPT`, `TEAM_SUPERVISOR_PROMPT`, 팀별 supervisor 프롬프트에 다음을 명시:
  - 라우팅 결정 규칙(어떤 신호를 봐야 하는지 — user_request, dispatched_workers, route_history, validator feedback 등)
  - 같은 워커/팀 재호출 시 정당화 요건
  - `request_human_review` / FINISH 트리거 조건
  - structured output 스키마 예: `{ "next": "<node|FINISH>", "reason": "<short>", "request_review": false, "team_finished": false }`
- 라우팅 LLM은 main LLM과 다른(저비용) 모델로 분리하는 옵션을 Phase 2 종료 후 평가 (이번 Phase에서는 같은 모델 사용)

### 4.1 Phase 2 Impact Map

| 변경 대상 | 직접 영향 |
| :--- | :--- |
| `packages/agent-core/src/agent_core/supervisor.py` (989 LOC, 603-LOC 단일 async 함수 포함) | head/team 라우팅 전면 LLM 위임, HITL 인터럽트 트리거 변경, `dispatched_workers`는 state 추적용으로 잔존 |
| 23개 정규식 + `_should_force_*` 분류 함수 | **삭제 대상** |
| 팀별 강제 순서 머신 (coding 67줄, data_science 25줄, research 29줄) | **삭제 대상** |
| 마법 상수 `HEAD_TEAM_REDIRECT_LIMIT`, `remaining_steps`, `max_team_dispatches` | 안전망으로 잔존, config 이동 |
| `validator.py`, `finalizer.py` 폴백 | LLM 라우팅 실패 시 fallback path로 재해석 |
| `load_memories.py` | 메모리 노드 (영향 적음) |
| `packages/prompt-kit/src/prompt_kit/prompts.py` | supervisor / team supervisor 프롬프트 전면 강화 (Phase 4.5와 합의) |
| 신규 `agent_core/safeguards.py`, `agent_core/router_schema.py`, `apps/backend/tests/routing_eval/` | LLM 결정 검증·차단 + structured output 스키마 + 골든 데이터셋 |

### 4.2 Phase 2 태스크 (LLM-Driven Routing 전환 반영)

- [x] 2.0 §4.0 정책을 `_workspace/llm_routing_policy.md`에 고정. 룰베이스 인벤토리(file:line)·safeguard 카테고리·evaluation 후속 일정 포함.
- [x] 2.1 `packages/agent-core/src/agent_core/config.py` 신설 — `SAFEGUARDS` dataclass에 4개 안전망 상수(head_team_redirect_limit, validator_remaining_steps, max_team_dispatches, structured_output_retry_count) + finalizer_recent_messages_limit. 기존 동작과 byte-identical 유지(아직 supervisor에 적용 전).
- [ ] 2.2 **휴리스틱 제거 Phase A — 정규식·`_should_force_*` 함수 삭제**. supervisor.py에서 23개 정규식 + 모든 `_should_force_*` 함수를 제거하고, 호출자(supervisor 본체)에서도 사용을 정리. trace/로그용 키워드 추출이 정말 필요한 경우만 `agent_core/text_keywords.py`로 격리(라우팅 결정과 분리). **본 세션 외(후속) — supervisor.py 989 LOC 재작성 위험으로 RouterDecision/safeguards 인프라(2.5/2.6) 위에서 점진 진행 필요**.
- [ ] 2.3 **휴리스틱 제거 Phase B — 팀별 강제 순서 머신 삭제**. supervisor.py의 coding/data_science/research 팀 강제 순서 블록을 삭제. team supervisor가 `dispatched_workers` state를 읽고 LLM이 결정하도록 위임. **본 세션 외(후속)**.
- [ ] 2.4 `supervisor_node()` 단순화 — head/team 모두 LLM 라우팅 + safeguards 호출 + structured output 파싱만 수행. 책임 분리: `agent_core/supervisors/head_supervisor.py`, `agent_core/supervisors/team_supervisor.py`(공통 라우터 본체). 팀별 모듈은 **프롬프트 차이만** 가짐(코드 중복 ≤ 1회). **본 세션 외(후속) — 2.2/2.3 직후 진행**.
- [x] 2.5 `agent_core/router_schema.py` 신설 — `RouterDecision`(next/reason/request_review/team_finished) + `RouterDecisionRecord`(상태 영속). LLM `with_structured_output` 사용 준비.
- [x] 2.6 `agent_core/safeguards.py` 신설 — `reject_invalid_goto`, `enforce_team_redirect_limit`, `enforce_dispatch_limit`, `fallback_decision_on_parse_failure` 순수 함수. `SafeguardOutcome` 결과 타입(status: accepted/rejected_invalid_goto/parse_failed/fallback_finish). **plan §4.0 P3 강제 — 결정 자체를 바꾸지 않고 차단·재요청만**. 단위 테스트 11 cases(`test_router_safeguards.py`).
- [ ] 2.7 supervisor / team-supervisor 프롬프트 강화 — `packages/prompt-kit/src/prompt_kit/prompts.py`에 §4.0.6 항목 반영. Phase 4.5(프롬프트 fragment 추출)와 충돌 없도록 사전 합의(공통 routing 지침은 fragment로 정의). **본 세션 외 — Phase 2.4 LLMRouter 적용과 동시 진행 권장**.
- [x] 2.8 라우팅 evaluation harness 골격 — `apps/backend/tests/routing_eval/` 신설: `golden_dataset.json`(12 cases 시작, 카테고리 8종 균등 분포: coding/coding-no-repo/research/data_science/vision/writing/FINISH/approval_request + ambiguous/multi-intent), `scorer.py`(`EvalCase`/`EvalReport`/`load_dataset`/`score_decisions` pure 함수), `test_scorer.py`(6 cases — dataset 로딩, top-1 hit/miss, request_review 별도 추적, category accuracy). 실 LLM 호출 + 50→100 case 확장 + nightly 실행은 Phase 2.4 LLMRouter 적용과 함께 진행. pytest 325 → **331 PASS**(+6, 회귀 0).
- [x] 2.9 finalizer/validator 에러 폴백 통일 — `agent_core/fallback_messages.py` 신설. `finalizer_absolute_fallback()`, `validator_recursion_warning()`, `validator_review_error()`, `validator_review_passed()`, `supervisor_safeguard_finish(reason)` 5개 helper. finalizer + validator 양쪽이 동일 출처에서 메시지 로드 — 사용자 가시 톤 일관성 확보. Phase 2.4 safeguard 발동 시 `supervisor_safeguard_finish(decision.reason)` 사용 준비 완료.
- [x] 2.10 `load_memories.py` 독립 테스트 — `apps/backend/tests/test_load_memories_node.py`가 이미 3 cases(skip-when-missing, populates-personalization, instruction-only-payload)로 커버 중. 인벤토리 확인 후 그대로 보존.
- [x] 2.11 finalizer messages 길이 상한 도입 — `SAFEGUARDS.finalizer_recent_messages_limit=200`. `make_finalizer_node` 내부에서 deduped 후 `[-N:]` 슬라이싱. 장기 대화 OOM 회귀 방지.
- [x] 2.12 `make_validator_node` alias 제거 — 외부 사용처 0건(builder.py, test 모두 `make_reviewer_node` 직접 사용) 확인 후 제거. validator.py에 주석으로 transition 완료 표시.
- [ ] 2.13 **Phase 2 통합 회귀** — 본 세션 인프라(2.0/2.1/2.5/2.6/2.10/2.11/2.12) 기준 pytest **311/311 PASS**(신규 11 router safeguards + 회귀 0). 휴리스틱 제거(2.2/2.3) + supervisor 단순화(2.4) + 프롬프트 강화(2.7) + evaluation(2.8) 완료 후 최종 통합 회귀는 후속 세션에서 routing eval ≥ 95% 정확도 + S2/S4/S5 스모크 추가 검증 예정.

### 4.3 Phase 2 태스크별 추가 검증 포인트

| 태스크 | VP 외 추가 점검 |
| :--- | :--- |
| 2.0 | 정책 문서가 §4.0과 일치. 룰베이스 인벤토리 표가 실제 코드 grep 결과와 일치 |
| 2.1 | 상수 변경 후 안전망 동작이 기존과 동일한지 — `test_supervisor_progression.py`, `test_validator_edge_cases.py` 통과 |
| 2.2 | `grep -rn "_should_force_\|_APPROVAL_PATTERNS\|_CODING_PATTERNS\|_DATA_SCIENCE_PATTERNS" packages/agent-core` 결과 0. 휴리스틱 의존 테스트가 LLM 라우팅 + 안전망 검증으로 교체되었는지 |
| 2.3 | 팀별 강제 순서 블록 삭제 후 dispatched_workers state는 여전히 갱신되는지(시각화·중복 방지용) |
| 2.4 | head supervisor / team supervisor가 동일 `LLMRouter` 본체를 호출하고 프롬프트만 다른 구조인지 — 코드 중복 ≤ 1회 |
| 2.5 | `RouterDecision` 스키마 위반 시 1회 재요청 → 그래도 실패 시 FINISH 폴백이 트레이스에 기록되는지. SSE `route` 이벤트 payload에 reason 노출 |
| 2.6 | safeguards 단위 테스트 — 각 함수가 LLM 결정을 변경하지 않고 차단/재요청만 수행하는지(P3 강제). 안전망 발동이 `route` 또는 별도 trace 이벤트로 노출 |
| 2.7 | 프롬프트 정책 테스트(`test_research_prompt_policy*.py`)를 확장해 routing 지시문·structured output 스키마 안내가 누락되지 않았는지 메타 검증 |
| 2.8 | 골든 데이터셋 50케이스가 §4.0.3의 카테고리를 균등 커버. evaluation 실행이 deterministic seed로 안정적 결과 산출. 비용 baseline 기록 |
| 2.13 | `_workspace/baselines/phase2/`에 final 저장. **라우팅 정확도/latency/토큰 비용 리포트** + Phase 1 baseline 대비 SSE/응답 shape 비교. P4 가시화가 SSE에 정확히 반영되는지 프론트 reducer와 교차 검증(integration-qa-protocol) |

---

## 5. Phase 3 — Frontend (3~5주)

**브랜치:** `refactor/phase-3-frontend-workspace` (main에서 분기). Phase 1.1·1.2(SSE 추출) 머지 후 시작이 안전. 분할 작업이 길어 태스크 서브 브랜치(`refactor/phase-3-frontend-workspace/<task-id>-<short>`) 사용을 적극 권장 — 컴포넌트 분할 단위로 PR 리뷰 부담 절감.

### 5.1 Phase 3 Impact Map

| 변경 대상 | 직접 영향 |
| :--- | :--- |
| `apps/frontend/src/components/workspace/WorkspaceRouteRoot.tsx` (2,635 LOC) | 모든 `/c/[threadId]` 화면, SSE 10종 이벤트 처리 |
| `handleStreamEvent` (L1410~1657) | SSE 파싱 + 상태 업데이트 |
| 18개 useState + 11개 useEffect | 스레드/스트림/액션스페이스 상태 |
| `apps/frontend/src/lib/api.ts` (592 LOC) | 모든 `/api/*` 호출, CSRF |
| Tailwind 인라인 클래스 | 모든 UI 표면 |

### 5.2 Phase 3 태스크

- [ ] 3.1 `handleStreamEvent`의 상태 업데이트 로직을 순수 reducer로 추출 → `lib/sse-reducer.ts` + 단위 테스트 (각 event_type별 5~10 케이스, FINAL_RESPONSE_STREAM_OWNERSHIP 명시적 검증 추가)
- [ ] 3.2 커스텀 훅 추출 — `hooks/useThreadCollection.ts`, `useActiveThread.ts`, `useStreamSession.ts`, `useActionSpace.ts`
- [ ] 3.3 WorkspaceRouteRoot 분할 — `components/workspace/StreamConsumer.tsx`, `MessageThreadView.tsx`, `ComposerPanel.tsx`, `WorkspaceSidebar.tsx`
- [x] 3.4 `lib/api.ts` 도메인 분할 (light-touch) — 공통 HTTP 플러밍을 `apps/frontend/src/lib/api/_client.ts`로 추출(API_BASE_URL, CSRF_COOKIE_NAME, CSRF_HEADER_NAME, UnauthorizedError, notifyUnauthorized, readCsrfToken, readErrorMessage, requestJson + RequestJsonOptions). 기존 `lib/api.ts`는 `_client`에서 재export — 도메인별 모듈(threads/chat/auth/memory/uploads/repositories/dashboard)로의 점진 마이그레이션은 후속(WorkspaceRouteRoot 분할 시점 동기). lint 0 errors, vitest 53/53, build PASS.
- [ ] 3.5 분할된 컴포넌트별 vitest 테스트 신설 (각 컴포넌트 최소 1개의 렌더링 + 핵심 인터랙션 케이스)
- [x] 3.6 Tailwind 디자인 토큰 추출 — Tailwind 4 environment(@theme inline)에 OrchAgent design token 10종을 매핑(`--color-oa-bg`/`-panel`/`-panel-strong`/`-panel-soft`/`-border`/`-border-soft`/`-accent`/`-accent-strong`/`-copy`/`-copy-soft`). `bg-oa-panel`, `text-oa-accent`, `border-oa-border` 등 유틸리티 즉시 사용 가능. 기존 `bg-[rgba(...)]` arbitrary value는 같은 CSS 변수를 가리키므로 점진 마이그레이션. lint 0E/0W, vitest 53/53, build PASS.
- [x] 3.7 `cn()` 유틸 중복 제거 — `apps/frontend/src/lib/cn.ts` 단일 출처(clsx + tailwind-merge). HITLPanel.tsx + WorkspaceRouteRoot.tsx의 중복 정의 제거 + `@/lib/cn` import로 통일. 동시에 L-001(`CodingSummaryPanels.tsx` 미사용 `EmptyCopy` import) + L-002(`RepoTreePanel.tsx` exhaustive-deps `diffs`) 해결. **lint 결과: 0 errors / 0 warnings** (이전 0E/2W → 0E/0W).
- [ ] 3.8 **Phase 3 통합 회귀** — `npm run lint && npm run test -- --run && node --test src/lib/chat-stream.test.mjs && npm run build`, S1~S7 전체 스모크

### 5.3 Phase 3 태스크별 추가 검증 포인트

| 태스크 | VP 외 추가 점검 |
| :--- | :--- |
| 3.1 | reducer가 순수함수임을 테스트로 강제 (동일 입력 → 동일 출력, 부작용 없음). FINAL_RESPONSE_STREAM_OWNERSHIP: 백엔드가 보낸 `text` 이벤트가 모두 동일 `run_id` 임을 확인하는 정합성 테스트 |
| 3.2 | 각 훅의 의존성 배열 정합성 — `react-hooks/exhaustive-deps` 린트 통과 |
| 3.3 | Props drilling 깊이 ≤ 2 (분할 후 측정). 자식이 부모 setState를 다단계로 받지 않는지 |
| 3.4 | 모든 fetch 호출이 `lib/api/_client.ts`의 공통 헬퍼를 거치는지(grep으로 raw `fetch(`/`axios` 잔재 0) |
| 3.5 | 컴포넌트 테스트가 분할 전 WorkspaceRouteRoot 동작과 동일 케이스를 커버 |
| 3.6/3.7 | 시각적 회귀 — 핵심 화면 스크린샷 baseline ↔ after 비교 (`_workspace/baselines/phase3/screenshots/`) |
| 3.8 | `_workspace/baselines/phase3/`에 final 저장. Phase 2 baseline 대비 SSE 소비 동작 동일 |

---

## 6. Phase 4 — Tools / Prompts / Infra (1~2주)

**브랜치:** `refactor/phase-4-tools-prompts-infra` (main에서 분기). Phase 2와 부분 병렬 가능. 4.5(프롬프트 fragment 추출)는 Phase 2 supervisor 분리 머지 후 시작.

### 6.1 Phase 4 Impact Map

| 변경 대상 | 직접 영향 |
| :--- | :--- |
| `packages/agent-tools/{web,coding,data,vision,file_io,runtime}.py` | 32개 공개 도구, 모든 워커 실행 경로 |
| `packages/prompt-kit/src/prompt_kit/prompts.py` (596 LOC, 25개 프롬프트) | 모든 supervisor/worker/validator 라우팅·생성 |
| `infra/compose/docker-compose.yml` | dev 스택 기동·헬스체크 |
| timeout 분산 (coding=180s, web=12s) | 장시간 작업 안정성 |

### 6.2 Phase 4 태스크

- [x] 4.1 agent-tools 공통 예외 처리 스키마 정의 — `packages/agent-tools/src/agent_tools/errors.py`에 `ToolError`(kind/message/details), `ToolErrorPayload`(ok=False+error), `make_tool_error_payload()` helper 신설. `ToolErrorKind` Literal(`input_validation`/`external_api`/`timeout`/`runtime`/`permission`/`not_found`/`unknown`). 단위 테스트 4 cases. **실제 도구 모듈 일괄 마이그레이션은 후속**(각 도구가 raise/문자열/dict 혼재 형식 → 통일 payload).
- [x] 4.2 runtime context 의존 도구 테스트 커버리지 보강 — `test_runtime_context.py` 신설(10 cases): get/set/reset 토큰 lifecycle, `attachment_manifest`/`resolve_runtime_attachment`/`list_runtime_attachments`/`artifact_path`, `register_runtime_artifact`(append+dedupe+outside-workspace 거부+missing-file 거부). pytest 315 → 325(+10).
- [x] 4.3 PDF/DOCX 추출 에러 경로 명세화 — `extract_document_text`에서 `ValueError`(unsupported kind) → `input_validation` ToolErrorPayload, `FileNotFoundError` → `not_found`, 그 외 모든 라이브러리 예외 → `runtime` 카테고리로 구조화. 사용자 가시 메시지에 `attachment_id` 포함.
- [x] 4.4 timeout 정책 통합 — `packages/agent-tools/src/agent_tools/config.py` 신설. `TIMEOUTS` dataclass(`coding_subprocess_seconds=180`, `web_http_seconds=12`, `runtime_context_default_seconds=60`). env override(`TOOL_TIMEOUT_CODING/_WEB/_DEFAULT`) 지원. 기본값은 기존 하드코딩 값과 byte-identical(coding.py 180s/web.py 12s 보존). 실제 도구 모듈의 import 적용은 후속.
- [x] 4.5 프롬프트 공통 fragment 모듈 신설 — `packages/prompt-kit/src/prompt_kit/fragments.py`에 `CRITICAL_GUIDELINES`/`WORKER_CONSTRAINTS`/`ROUTER_DECISION_GUIDANCE`(Phase 2.7 routing 지침)을 정의. `prompts.py`의 실 fragment 통합은 후속(supervisor LLM-Driven Router 적용과 동시 진행).
- [x] 4.6 복잡 도구 docstring/예제 보강 — `apply_patch_edit`(literal whitespace + first-occurrence semantics + repo-relative path + 성공/실패 응답 shape + 예시), `python_repl_data_tool`(pre-imported library + sandbox restrictions + 차트 저장 가이드 + 예시), `verify_local_page`(localhost-only enforcement + 본문 truncate 4000자 + 응답 shape + 예시).
- [x] 4.7 docker-compose 헬스체크 확장 — backend `/api/health` python urllib healthcheck(interval=10s, timeout=5s, retries=6, start_period=30s) + frontend root node http healthcheck(interval=15s, timeout=5s, retries=8, start_period=60s). 부팅 대기 신호 명확화.
- [x] 4.8 **Phase 4 통합 회귀** — pytest **325/325 PASS** (4.1 ToolErrorPayload 4 + 4.2 runtime context 10 신규 + 회귀 0). Phase 0 baseline 275 대비 +50 신규(전체 phase 누적). S2/S3/S5 dev E2E는 Phase 5 통합 회귀에서 묶어 진행.

### 6.3 Phase 4 태스크별 추가 검증 포인트

| 태스크 | VP 외 추가 점검 |
| :--- | :--- |
| 4.1 | 워커가 받은 도구 에러 페이로드를 supervisor·validator가 정확히 해석하는지 (`test_validator_edge_cases.py` 확장) |
| 4.2 | 도구 직접 실행 단위 테스트 vs runtime context 통합 테스트 분리 |
| 4.3 | UI에서 데이터 분석 실패 메시지가 사용자에게 어떻게 표시되는지 — S2/S5 스모크에 케이스 추가 |
| 4.4 | 장시간 코딩 작업 시뮬레이션(timeout 직전 종료) 케이스 |
| 4.5 | 메타 테스트 — 추출된 fragment가 각 프롬프트에 정확히 포함되는지 (`test_research_prompt_policy*.py`에 fragment presence 케이스) |
| 4.7 | `docker compose -f infra/compose/docker-compose.yml up`이 healthcheck 통과 후 ready 신호를 명확히 출력 |
| 4.8 | `_workspace/baselines/phase4/`에 final 저장 |

---

## 7. Phase 5 — 최종 회귀 + 문서화 (1주)

**브랜치:** `refactor/phase-5-final-regression` (main에서 분기 — Phase 1~4 모두 머지 완료 후 시작). main이 phase 1~4의 모든 변경을 누적한 상태여야 한다.

- [ ] 5.0 모든 phase 브랜치 main 머지 확인 — `git log --oneline --merges main | grep refactor-phase` 등으로 머지 이력 점검. 미머지 phase가 있으면 본 phase 진입 보류
- [x] 5.1 전체 pytest 통과 — **315/315 PASS** (Phase 0 baseline 275 대비 +40 신규, 회귀 0). 신규 분포: response_collector 10 + event_processor 15 + router safeguards 11 + tool errors 4.
- [x] 5.2 전체 frontend 테스트 통과 — `npm run lint`(0 errors, 2 known warnings L-001/L-002), `npm run test -- --run`(vitest 53/53 PASS, 1회 flaky 후 재실행 PASS), `node --test src/lib/chat-stream.test.mjs`(3/3 PASS).
- [x] 5.3 frontend production build 통과 — `npm run build` PASS. 11개 페이지(`/`, `/_not-found`, `/c/[threadId]` dynamic, `/dashboard`, `/login`, `/settings/*` × 3, `/signup`) 모두 정상 컴파일.
- [x] 5.4 dev 스택 위 E2E 스모크 시나리오 통과(S1+S2+S3+S6) — playwright MCP로 실행. **S3 결과**: `https://www.python.org` 검색 요청 → Research Team(Search + Web Scraper) → Finalizer 5 steps 라우팅, 도구 활동 카드 정상(Completed Tavily Search / Scrape Webpages), 응답 + 근거 링크 + Head/Team Supervisor reasoning 4종 모두 정상. S4/S5/S7은 별도 시나리오로 후속.
- [x] 5.5 SSE 계약 회귀 검증 — backend 15(`test_event_processor`) + 10(`test_response_collector`) + frontend 3(`chat-stream.test.mjs`) + S1+S2+S3+S6 E2E 모두 PASS. 백엔드 emit ↔ 프론트 reducer 양쪽 검증 완료, 회귀 0.
- [x] 5.6 README/AGENTS.md 갱신 — Project Structure에 신규 모듈(`services/streaming`, `services/orchestration_service`, `services/event_recording_service`, `schemas/{turn,message}`, `agent_core/{config,router_schema,safeguards,fallback_messages}`, `agent_tools/{config,errors}`, `prompt_kit/fragments`, `lib/cn`, `infra/scripts/{capture,diff}_baseline`) 반영. AGENTS.md에 새 라우팅 정책(P1~P5) + seam(`OrchestrationService`) 명시.
- [ ] 5.7 본 plan 상단 요약 블록의 "최종 수정일시" 갱신 + 모든 phase 체크박스 `- [x]` 확인

---

## 8. 의존성 그래프 & 병렬화 전략

```
Phase 0 (검증 인프라)
   │
   ├─► Phase 1 Backend ───┐
   │                       │
   ├─► Phase 2 LangGraph ──┼──► Phase 5 최종 회귀 + 문서
   │                       │
   ├─► Phase 3 Frontend ───┤
   │                       │
   └─► Phase 4 Tools ──────┘
```

- **Phase 1과 Phase 2는 부분 병렬 가능** — 단 1.5(orchestration_service)는 2.4(supervisor 단순화)에 의존. Phase 2를 먼저 끝낸 뒤 1.5를 진행하는 게 안전.
- **Phase 3은 Phase 1.1·1.2(SSE 추출)에 약한 의존** — Phase 1.1/1.2 직후 시작 가능. SSE 이벤트 shape이 안정화된 시점이 분기점. 또한 Phase 2.5/2.6(RouterDecision + safeguards 가시화)에서 `route` 이벤트 payload가 reason·request_review 필드를 포함하게 되므로 Phase 3.1(SSE pure reducer)는 Phase 2.5 합의 후 진행하면 충돌이 적다.
- **Phase 4는 Phase 2와 부분 병렬 가능** — 다만 **Phase 4.5(프롬프트 fragment 추출)와 Phase 2.7(supervisor 프롬프트 강화)은 prompt-kit를 동시에 건드리므로 사전 합의 필수**. 작업 순서 권장: Phase 2.7 초안 → Phase 4.5 fragment 추출 → Phase 2.7 fragment 활용으로 마무리.
- **각 phase는 독립 PR**로 머지 가능해야 함. PR 머지 직전에 §1.5 회귀 한 번 더 실행.

권장 진행 순서: **Phase 0 → Phase 1 (1.1~1.4) ↘ Phase 2 (2.0~2.6)** 병렬 → **Phase 2 (2.7~2.8) ↔ Phase 4.5 합의 진행** → **Phase 1 (1.5~1.10) + Phase 3** 병렬 → **Phase 4 잔여** → **Phase 5**.

---

## 9. 부록 A. 기존 plans와의 관계 (Phase 0.4에서 확정)

| 기존 plan | 영역 | 본 리팩토링과의 관계 | 처리 방안(채워야 함) |
| :--- | :--- | :--- | :--- |
| ASYNC_STREAM_DB_CLEANUP_REFACTOR_PLAN.md | backend chat.py | 직접 중첩 | Phase 1.3/1.4에 흡수 검토 |
| FINAL_RESPONSE_STREAM_DUPLICATION_REFACTOR_PLAN.md | backend collector | 직접 중첩 | Phase 1.1에 흡수 검토 |
| STALE_FALLBACK_ON_INTERRUPT_FIX_PLAN.md | backend/HITL | 부분 중첩 | Phase 1.2 또는 Phase 2.5에 흡수 검토 |
| HIERARCHICAL_MODERNIZATION_PLAN.md | agent-core/workflow | 직접 중첩 | Phase 2에 흡수 검토 |
| PHASE_1_1_NATIVE_SUBGRAPH.md | workflow | 부분 중첩 | Phase 2 의존성 확인 |
| SUPERVISOR_INTENT_ROUTING_SCHEMA_PLAN.md | supervisor | 직접 중첩 (라우팅 정책) | **Phase 2.0~2.5(LLM-Driven Routing 전환)에 흡수 검토**. 본 plan의 §4.0 정책이 우선. RouterDecision schema·SSE route 페이로드는 Phase 2.5와 합치 |
| CODING_TEAM_PINGPONG_FIX_PLAN.md | supervisor coding | 부분 중첩 (강제 순서 제거) | **Phase 2.3 휴리스틱 제거 + 2.7 프롬프트 강화에 흡수 검토**. ping-pong 방지 의도는 프롬프트의 "재호출 정당화 요건" + safeguards `enforce_team_redirect_limit`로 대체 |
| PLANNER_RESEARCH_PROMPT_POLICY_REFACTOR_PLAN.md | prompts | 부분 중첩 (프롬프트 정책) | **Phase 2.7 + Phase 4.5와 합치**. 공통 routing 지침 fragment·라우팅 메타 테스트가 정합되도록 합의 |
| THREAD_HISTORY_SIDEBAR_REFACTOR_PLAN.md | frontend | 부분 중첩 | Phase 3.2/3.3 후 잔여 항목 확인 |
| FIGMA_WORKSPACE_UI_REFACTOR_PLAN.md | frontend | 부분 중첩 | Phase 3.3/3.6 후 잔여 항목 확인 |
| CODING_AGENT_MINIMAX_INSPIRED_UI_PLAN.md | frontend | 부분 중첩 | Phase 3 후 진행 |
| BACKEND_QA_TEST_PLAN.md | backend tests | 보완적 | Phase 1 통합 회귀에 흡수 |
| CHAT_THREAD_URL_ROUTING_PLAN.md | frontend routing | 부분 중첩 | Phase 3.1(workspace host 분할) 머지 후 진행 |
| AGENTIC_UI_PLAN.md | frontend | 부분 중첩 | Phase 3 완료 후 진행 |
| AI_THREAD_TITLE_SUMMARIZATION_PLAN.md | frontend/prompts | 부분 중첩 | Phase 3 + Phase 4.5 완료 후 잔여 점검 |
| CODING_TEAM_CONTROL_PLANE_AND_UI_PLAN.md | backend/frontend | 부분 중첩 | Phase 2.3 + Phase 3 완료 후 진행 |
| CODING_TEAM_REPO_WORKSPACE_PLAN.md | backend | 부분 중첩 | Phase 2 머지 후 Phase 3~4 사이 진행 |
| CURRENT_STABILIZATION_TODO.md | backend/infra 안정화 | 무관 | §1.6 E2E 스모크에 흡수 가능 항목만 재활용 |
| DATA_SCIENCE_ANALYTICS_TEAM_PLAN.md | agent-core/backend/frontend | 신규 기능 | Phase 2 완료 후 별도 cycle |
| LANGGRAPH_POSTGRES_LONG_TERM_MEMORY_REFACTOR_PLAN.md | backend/agent-core | 부분 중첩 | Phase 4 완료 후 별도 cycle |
| LONG_TERM_MEMORY_PERSONALIZATION_PLAN.md | frontend/backend | 신규 기능 | Phase 2 완료 후 별도 cycle |
| MULTIMODAL_PLAN.md | agent-core/backend | 신규 기능 | Phase 2 완료 후 별도 cycle |
| PATCH_ENDPOINT_EVOLUTION_PLAN.md | backend/frontend | 부분 중첩 | Phase 1.6 + Phase 3 중간 진행 |
| PERSONAL_MEMORY_CUSTOM_INSTRUCTIONS_PLAN.md | backend/frontend | 신규 기능 | Phase 4 완료 후 별도 cycle |
| PHASE_3_ADVANCED_FEATURES_PLAN.md | agent-core | 직접 중첩 | Phase 3 또는 Phase 2 후속에 흡수(HITL 관련) |
| PHASE_4_AGENT_EXPANSION_PLAN.md | agent-core | 직접 중첩 | Phase 4 영역과 정합 검토 |
| PINNED_THREAD_TOP_ORDER_PLAN.md | backend/frontend | 부분 중첩 | Phase 3.1 머지 후 진행 |
| SIGNUP_AUTH_SYSTEM_PLAN.md | backend/frontend | 신규 기능 | Phase 1 머지 후 독립 보안 cycle |
| UPLOADS_ENDPOINT_EVOLUTION_PLAN.md | backend | 부분 중첩 | Phase 4.3 + 운영 정책 검토 후 진행 |
| USER_TRACING_ANALYTICS_SCHEMA_PLAN.md | backend | 신규 기능 | Phase 1 머지 후 별도 cycle |

> 본 표는 Phase 0.4에서 30개 plan을 1회 훑은 뒤 확정됨(2026-05-19). 상세 분류·미체크 카운트·근거는 `_workspace/plans_overlap_inventory.md` 참조.
>
> 그룹 합계: 직접 중첩 12 · 부분 중첩 11 · 신규 기능 6 · 무관 1 = 30개.

---

## 10. 부록 B. baseline 캡처 명령어 모음(재사용 스니펫)

```bash
# 디렉토리
mkdir -p _workspace/baselines/<task_id>

# Backend
cd apps/backend
uv run pytest tests/ -v --tb=line 2>&1 | tee ../../_workspace/baselines/<task_id>/pytest_before.log
cd -

# Frontend
cd apps/frontend
npm run lint 2>&1 | tee ../../_workspace/baselines/<task_id>/lint_before.log
npm run test -- --run 2>&1 | tee ../../_workspace/baselines/<task_id>/vitest_before.log
node --test src/lib/chat-stream.test.mjs 2>&1 | tee ../../_workspace/baselines/<task_id>/nodetest_before.log
cd -

# API 응답 샘플 (dev 백엔드 :8002 가정, 인증 쿠키 cookies.txt)
for path in threads "threads/<thread_id>/messages" "dashboard/summary" "users/me/memory/settings"; do
  curl -s -b cookies.txt "http://localhost:8002/api/$path" \
    | jq . > _workspace/baselines/<task_id>/$(echo $path | tr '/' '_')_before.json
done

# OpenAPI 스키마
curl -s http://localhost:8002/openapi.json | jq . > _workspace/baselines/<task_id>/openapi_before.json
```

`after`는 동일 명령에서 파일명만 `_after.*`로 바꾼다. diff 명령은 §1.5 참고.

---

## 11. 진행 체크포인트 요약

| Phase | 기간 | 브랜치명 | 핵심 변경 파일 수 | 회귀 검증 우선 시나리오 |
| :--- | :--- | :--- | :--- | :--- |
| 0 | 1~2일 | `refactor/phase-0-foundation` | 0 (스크립트/문서만) | baseline 캡처 자체가 PASS |
| 1 | 3~4주 | `refactor/phase-1-backend-cohesion` | 라우터 1 + 신설 서비스 6~8 + 스키마 2 | S1, S2, S3, S4, S5 |
| 2 | 3~4주 | `refactor/phase-2-langgraph-core` | supervisor 분리·휴리스틱 제거 5~6 + safeguards + router_schema + routing_eval + prompts | S2, S4, S5 + routing eval 정확도 ≥ 95% |
| 3 | 3~5주 | `refactor/phase-3-frontend-workspace` | WorkspaceRouteRoot 분할 4~5 + hooks 4 + api 도메인 7 | S1~S7 전체 |
| 4 | 1~2주 | `refactor/phase-4-tools-prompts-infra` | tools 6 + prompt fragment + infra | S2, S3, S5 + 도구 단위 테스트 |
| 5 | 1주 | `refactor/phase-5-final-regression` | 0 (문서/검증) | S1~S7 전체 + 모든 baseline diff 0 + routing eval 재실행 |

---

## 12. 브랜치 / PR 전략 상세

### 12.1 네이밍 규약

| 종류 | 패턴 | 예 |
| :--- | :--- | :--- |
| Phase 브랜치 | `refactor/phase-<N>-<scope>` | `refactor/phase-1-backend-cohesion` |
| 태스크 서브 브랜치(선택) | `refactor/phase-<N>-<scope>/<task-id>-<short>` | `refactor/phase-1-backend-cohesion/1.1-response-collector` |
| 핫픽스 | `fix/<scope>-<summary>` | `fix/auth-expired-reset-token` |
| 머지 태그 | `refactor-phase-<N>-complete` | `refactor-phase-1-complete` |

- `<scope>`는 phase 이름의 단순 슬러그(`backend-cohesion`, `langgraph-core`, `frontend-workspace`, `tools-prompts-infra`, `final-regression`).
- 태스크 서브 브랜치는 phase 브랜치를 base로 분기하고 phase 브랜치로 PR 머지(중첩 PR). main 직행 금지.

### 12.2 분기·동기화 규칙

1. Phase 브랜치는 항상 **최신 main에서 분기**한다. Phase N+1 시작 시점에 Phase N이 머지되어 있으면 자동으로 누적 변경을 반영.
2. Phase 진행 중 다른 phase가 main에 머지되면, 다음 태스크 시작 전에 phase 브랜치를 `git pull --rebase origin main`(또는 merge)으로 동기화. 충돌은 즉시 해결, 해결 직후 §1.3~§1.5 단위/통합/회귀 재실행.
3. 태스크 서브 브랜치는 phase 브랜치를 베이스로 한다. phase 브랜치가 main과 동기화되면 서브 브랜치도 rebase.
4. 강제 푸시(`--force-with-lease`)는 **본인 phase/태스크 브랜치에 한해서만** 허용. main과 phase 브랜치의 force push는 금지.

### 12.3 PR 정책

- **PR 단위**: phase 브랜치 → main PR이 phase 머지의 단일 진입점. 태스크 서브 브랜치는 phase 브랜치를 향한 내부 PR.
- **PR 제목**: `refactor(<scope>): <phase summary>` 또는 태스크 PR이면 `refactor(<scope>): <task-id> <summary>`.
- **PR 본문 필수 항목**:
  - 변경 요약(어떤 파일·심볼이 어떻게 이동/분리)
  - Impact Map 링크 (`_workspace/refactor_impact_<task_id>.md`)
  - Baseline diff 결과 요약(PASS 수 before/after, 응답 shape diff 없음 확인)
  - 수동 E2E 스모크 결과(`S1~S7` 중 영향 항목)
  - 롤백 방법(머지 SHA + revert 명령)
- **리뷰 / 자체 점검**:
  - 단독 작업이라면 self-review 체크리스트(§1.7 롤백 기준)를 PR 본문에 그대로 첨부하고 모두 PASS.
  - 코드 리뷰 가능 환경이면 phase별 PR은 외부 리뷰 필수.
- **머지 게이트**:
  - §1.5 회귀 baseline diff 0 + §1.6 영향 시나리오 PASS + CI(있으면) 통과.
  - phase 브랜치 → main 머지는 **`git merge --no-ff`**로 머지 커밋 생성(추적성). 머지 커밋 메시지 형식:
    ```
    refactor(<scope>): merge phase <N> — <one-line summary>

    - <bullet 1>
    - <bullet 2>
    Plan: plans/CODEBASE_WIDE_REFACTORING_PLAN.md §<N>
    ```
- **머지 후 동작**:
  - 머지 직후 `refactor-phase-<N>-complete` 태그.
  - 진행 중인 다른 phase 브랜치들은 §12.2.2 동기화 절차 수행.

### 12.4 충돌·롤백 절차

| 상황 | 조치 |
| :--- | :--- |
| Phase 브랜치 작업 중 main 변경과 충돌 | `git pull --rebase origin main` → 충돌 해결 → §1.3 단위 재실행 → §1.5 회귀 재실행 |
| 다른 phase가 같은 파일을 수정 | 후행 phase가 selected merge 후 §1.5 회귀 통과 책임. 영향 큰 경우 phase 간 순서 재조정(§8 의존성 그래프) |
| 머지 후 회귀 발견 | `git revert -m 1 <merge_sha>`로 phase 단위 revert → revert 커밋 PR → 재머지 전에 원인 분석·재구현 |
| 단일 태스크 회귀 | phase 브랜치 내에서 해당 태스크 커밋만 `git revert <task_sha>`. phase 전체 revert 금지 |
| 핫픽스 충돌 | 핫픽스는 main 머지를 우선. 진행 중인 phase 브랜치는 머지 후 rebase로 흡수 |

### 12.5 보호 정책

- **main**: 직접 push 금지, PR 필수, 회귀 게이트 PASS 필수, force push 금지.
- **phase 브랜치**: 본인 외 push 금지(공동 작업 시는 owner 합의), force push는 `--force-with-lease`만, 머지 PR 생성 후 history rewrite 금지.
- **태그**: 머지 완료 phase의 태그는 삭제·재할당 금지.

이 정책은 Phase 0의 `_workspace/branch_protection_policy.md`에 동일 내용을 복제·합의·기록한다.

---

**작성 메모.** 본 문서는 `_workspace/refactor_audit_*.md` 4종을 1차 감사 결과로 사용했다. 각 phase 진입 시 해당 audit 문서의 file:line 근거를 다시 열어 Impact Map을 갱신한다. 실제 코드 변경은 본 plan의 체크박스 진행 순서를 따른다.
