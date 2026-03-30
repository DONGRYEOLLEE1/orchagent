---
작업명: Personal Memory Custom Instructions Plan
간단요약: 기존 Personal Memory 화면 하단에 명시적 개인화 지침 목록을 추가하고, backend/frontend/runtime prompt 주입 경로를 memory와 분리된 explicit-instructions 레이어로 단계적으로 확장한다.
작성일시: 2026-03-28 19:10 KST
최종 수정일시: 2026-03-30 16:09 KST
---

# Personal Memory Custom Instructions Plan

## 배경

`docs/PERSONAL_MEMORY_CUSTOM_INSTRUCTIONS_RESEARCH_REPORT.md` 조사 결과와 현재 코드베이스를 다시 훑어본 결과, 이번 작업은 단순히 `personal memory` 목록 아래에 카드 몇 개를 추가하는 수준으로 처리하면 안 된다.

현재 코드베이스는 이미 다음 기반을 갖고 있다.

- `apps/frontend/src/components/settings/PersonalMemoryPanel.tsx`
  - `Personal Memory` 전용 settings surface
- `apps/backend/api/routes/memory.py`
  - memory settings/list/create/delete API
- `apps/backend/workflow/load_memories.py`
  - turn 시작 시 personalization memory load
- `packages/agent-core/src/agent_core/personalization.py`
  - personalization prompt block renderer
- `packages/agent-core/src/agent_core/supervisor.py`
  - supervisor prompt에 personalization block 합성
- `packages/agent-core/src/agent_core/nodes/finalizer.py`
  - finalizer prompt에 personalization block 합성
- `apps/backend/services/memory_agent_service.py`
  - 이미 `language_preference`, `response_format`, `tone_style`, `technical_stack` 같은 inferred category를 추출 가능

하지만 현재 구조에는 다음 공백이 있다.

- 사용자가 명시적으로 `말투`, `응답 형식`, `나에 대한 배경지식`을 관리하는 UI가 없다.
- inferred memory와 explicit instruction을 구분하는 데이터 모델이 없다.
- personalization은 현재 하나의 `USER PERSONALIZATION MEMORY` soft block으로만 주입된다.
- 사용자가 입력한 자유문을 그대로 system/developer 수준으로 넣으면 policy override 리스크가 생긴다.

즉 이번 작업의 핵심은 `memory를 늘리는 것`이 아니라, `explicit personalization instructions` 레이어를 현재 memory path 옆에 올바르게 추가하는 것이다.

## 목표

- `Personal Memory` 화면 하단에 `Personalization Instructions` 섹션을 추가한다.
- explicit instruction 저장소를 existing memory 저장소와 분리한다.
- runtime prompt에 `profile / instructions / memory`를 분리된 블록으로 주입한다.
- `현재 턴의 사용자 요청 우선` 규칙을 system policy로 고정한다.
- personalization 관련 backend/frontend/test 경로를 현재 코드베이스 구조에 맞게 단계적으로 확장한다.

## 범위

- 포함
  - explicit instruction용 DB 모델/서비스/API
  - 기존 `user_memory_settings` 확장 또는 동등한 settings 확장
  - `load_memories` personalization payload 확장
  - `prompt-kit` 기반 personalization policy/prompt 계약 정리
  - `PersonalMemoryPanel` 확장
  - backend/frontend 회귀 테스트
- 제외
  - temporary chat / incognito mode 도입
  - inferred memory를 explicit instruction으로 자동 승격
  - 응답 하단의 personalization provenance UI 노출
  - settings route 명 변경 (`/settings/personal-memory` 유지)

## 코드베이스 제약 및 전제

- 런타임 LLM 초기화는 계속 `langchain.chat_models.init_chat_model`을 사용한다.
- worker agent 생성은 계속 `langchain.agents.create_agent`를 사용한다.
- system prompt/policy text는 반드시 `packages/prompt-kit/src/prompt_kit/prompts.py`로 모은다.
- backend schema는 Alembic migration보다 `Base.metadata.create_all()` + `SchemaPatchService` 패턴이 강하다.
- 새 테이블은 `Base.metadata.create_all()`로 생성 가능하지만, 기존 `user_memory_settings`에 컬럼을 추가하면 `SchemaPatchService` 확장이 필요하다.
- frontend에는 범용 modal/dialog 인프라가 사실상 없으므로 v1 편집 UX는 `PersonalMemoryPanel` 안의 inline composer/editor를 우선한다.
- 현재 personalization 주입은 supervisor/finalizer 양쪽에서 동일 renderer를 쓰므로, 새 instruction block도 이 공통 renderer 한 곳에서 관리해야 한다.

## 설계 원칙

### 1. memory와 instructions를 분리한다

- `memory`
  - retrieval/search/summary 중심
  - inferred + explicit memory card
  - soft context
- `instructions`
  - user-authored explicit preference
  - 항상 deterministic order로 로드
  - 현재 요청보다 낮지만 기존 memory보다는 강한 기본값

### 2. 자유문 raw text를 system policy로 승격하지 않는다

저장 시점에 아래 규칙을 둔다.

- 허용 범위
  - `response_style`
  - `user_profile`
- 비허용 범위
  - tool 사용 정책 변경
  - approval 우회
  - safety/business rule override

### 3. prompt는 세 블록으로 분리한다

- `USER PERSONALIZATION PROFILE`
- `USER RESPONSE PREFERENCES`
- `USER MEMORY NOTES`

그리고 공통 policy는 반드시 명시한다.

- 현재 턴의 사용자 요청 우선
- personalization은 시스템 정책이 아님
- 충돌 시 현재 요청 우선, 필요 시 clarification

### 4. explicit instructions는 memory store가 아니라 SQL canonical source를 우선한다

현재 `MemoryStoreService`는 summary + recent retrieval용이다. explicit instructions는 데이터 양이 작고 항상 전량 로드가 더 자연스러우므로, v1에서는 memory store에 섞지 않고 SQL canonical source를 유지한다.

## 권장 구현 방향

### 데이터 계층

- 기존 `apps/backend/models/user_memory.py`에 explicit instruction 모델을 인접 배치한다.
- 새 SQLAlchemy 모델 권장 이름:
  - `UserPersonalizationInstruction`
- 기존 `UserMemorySettings`에는 `instructions_enabled`를 추가한다.
- `models/__init__.py`에 새 모델 등록을 추가한다.

### API 계층

실무적으로는 기존 `apps/backend/api/routes/memory.py` 안에서 새 path를 추가하는 편이 churn이 적다.

- `GET /api/users/me/personalization/settings`
- `PATCH /api/users/me/personalization/settings`
- `GET /api/users/me/personalization/instructions`
- `POST /api/users/me/personalization/instructions`
- `PATCH /api/users/me/personalization/instructions/{instruction_id}`
- `DELETE /api/users/me/personalization/instructions/{instruction_id}`

파일은 기존 router를 재사용하되, 외부 path namespace는 `personalization`으로 분리한다.

### 런타임 계층

- `workflow/load_memories.py`는 파일명을 당장 바꾸지 않고, memory + instructions를 함께 싣는 personalization loader로 확장한다.
- SQL-based explicit instructions load는 전용 service에서 처리한다.
- prompt block assembly는 `packages/agent-core/src/agent_core/personalization.py` 한 곳에서 수행한다.
- 새 policy 문구는 `packages/prompt-kit/src/prompt_kit/prompts.py`에 정의하고 import 해서 사용한다.

### 프런트엔드 계층

- `/settings/personal-memory` route는 유지한다.
- `PersonalMemoryPanel` 아래에 `Personalization Instructions` 섹션을 추가한다.
- v1 편집은 inline form/card 패턴으로 구현한다.
- 새 페이지를 만들지 않고 기존 panel 확장으로 끝낸다.

## 검증 전략

### 백엔드 최소 검증

- `uv run pytest apps/backend/tests/test_memory_api.py -v`
- `uv run pytest apps/backend/tests/test_load_memories_node.py -v`
- `uv run pytest apps/backend/tests/test_supervisor.py -v`
- `uv run pytest apps/backend/tests/test_finalizer_node.py -v`
- `uv run pytest apps/backend/tests/test_startup.py -v`
- 새 instruction API/서비스/스키마 테스트 파일 추가 시 해당 테스트 포함

### 프런트엔드 최소 검증

- `cd apps/frontend && npm run lint`
- `cd apps/frontend && npm run test -- personal-memory`
- `cd apps/frontend && npm run build`

## Phase 1. Schema, Settings, API Contract

목표:

- explicit instructions의 canonical persistence와 API surface를 먼저 만든다.
- 기존 `user_memory_settings` 확장 시 startup patch 경로를 함께 마련한다.

태스크:

- [x] `apps/backend/models/user_memory.py`에 `UserPersonalizationInstruction` 모델을 추가한다.
- [x] `apps/backend/models/user_memory.py`의 `UserMemorySettings`에 `instructions_enabled` 컬럼을 추가한다.
- [x] `apps/backend/models/__init__.py`에 새 모델을 등록한다.
- [x] `apps/backend/services/schema_patch_service.py`에 `user_memory_settings.instructions_enabled` 보강 patch를 추가한다.
- [x] `apps/backend/main.py` startup 초기화 경로에 새 schema patch 호출을 추가한다.
- [x] explicit instruction용 Pydantic schema를 정의한다.
- [x] explicit instruction용 service (`list/create/update/delete/toggle/sanitize`)를 추가한다.
- [x] `apps/backend/api/routes/memory.py`에 `/users/me/personalization/settings` 및 `/users/me/personalization/instructions*` endpoint를 추가한다.
- [x] settings response에 `instructions_enabled`를 포함한다.
- [x] 기존 memory settings와 personalization settings의 관계를 문서 주석/코드 주석 수준에서 명확히 정리한다.
- [x] backend API 테스트 파일을 추가 또는 확장하여 settings/instruction CRUD를 검증한다.
- [x] startup/schema 관련 테스트를 확장하여 새 patch 호출과 metadata 등록을 검증한다.

검증 기준:

- 새 테이블이 metadata에 등록된다.
- 기존 DB에 `instructions_enabled`가 없어도 startup patch로 보강된다.
- 인증/CSRF 규칙을 유지한 채 CRUD가 동작한다.

## Phase 2. Runtime Personalization Injection Refactor

목표:

- explicit instructions를 memory와 분리된 블록으로 supervisor/finalizer prompt에 주입한다.
- 현재 요청 우선 규칙을 prompt contract에 고정한다.

태스크:

- [ ] personalization policy/renderer에 필요한 문구를 `packages/prompt-kit/src/prompt_kit/prompts.py`로 이동 또는 추가한다.
- [ ] `packages/agent-core/src/agent_core/personalization.py`를 `profile / instructions / memory` 블록 렌더링 방식으로 확장한다.
- [ ] `apps/backend/services`에 runtime personalization payload를 조립하는 전용 orchestration service를 추가한다.
- [ ] `apps/backend/workflow/load_memories.py`가 memory store payload와 explicit instruction payload를 함께 조립하도록 확장한다.
- [ ] `shared_context.personalization` 구조를 `context_block` 단일 필드에서 분리된 block 중심 구조로 확장한다.
- [ ] `shared_context.personalization_meta`에 `instruction_ids`, `instruction_count`, `instructions_enabled`를 추가한다.
- [ ] `packages/agent-core/src/agent_core/supervisor.py`가 새 personalization renderer 출력만 참조하도록 유지한다.
- [ ] `packages/agent-core/src/agent_core/nodes/finalizer.py`도 같은 renderer 출력만 참조하도록 유지한다.
- [ ] explicit instruction은 SQL canonical source에서 deterministic order로 로드하고, 기존 `MemoryStoreService`는 soft memory retrieval만 담당하도록 경계를 명확히 한다.
- [ ] current-turn override 규칙을 prompt policy와 테스트 양쪽에 반영한다.
- [ ] prompt injection 범위를 벗어나는 instruction text가 저장/렌더링되지 않도록 validator를 service layer에 추가한다.
- [ ] `test_load_memories_node.py`를 확장해 instruction payload merge를 검증한다.
- [ ] `test_supervisor.py`와 `test_finalizer_node.py`에 personalization block 반영 여부를 캡처하는 테스트를 추가한다.

검증 기준:

- instruction과 memory가 prompt에서 서로 다른 섹션으로 렌더링된다.
- 최신 사용자 요청 우선 규칙이 prompt policy에 포함된다.
- explicit instruction이 있어도 기존 memory retrieval summary/recent path는 유지된다.

## Phase 3. Settings UI and Client Integration

목표:

- 현재 `PersonalMemoryPanel`에 explicit instructions 관리 UI를 붙인다.
- 새 route를 만들지 않고 기존 settings 정보 구조를 유지한다.

태스크:

- [ ] 프런트 타입을 `memory.ts` 확장 또는 새 `personalization.ts` 분리 방식으로 정리한다.
- [ ] `apps/frontend/src/lib/api.ts`에 personalization settings/instructions fetch/create/update/delete 함수들을 추가한다.
- [ ] `apps/frontend/src/components/settings/PersonalMemoryPanel.tsx`에 `Personalization Instructions` 섹션을 추가한다.
- [ ] `Instructions Policy` 토글 또는 동등한 overall enable control을 추가한다.
- [ ] instruction card에 `type`, `title`, `content`, `enabled`, `...` action을 렌더링한다.
- [ ] v1 편집 UX는 modal 대신 inline composer/editor로 구현한다.
- [ ] add/create 흐름과 edit/update 흐름에서 validation error, saving state, optimistic update 범위를 정리한다.
- [ ] empty state, loading state, API error state를 explicit instructions에도 추가한다.
- [ ] `apps/frontend/src/app/settings/personal-memory/page.test.tsx`를 확장하거나 새 컴포넌트 테스트를 추가한다.
- [ ] 기존 memory card hover/menu 상호작용과 새로운 instruction 편집 상호작용이 충돌하지 않는지 확인한다.

검증 기준:

- `/settings/personal-memory` 하나의 화면에서 memory와 instructions를 모두 관리할 수 있다.
- inline create/edit/delete/toggle 흐름이 테스트로 커버된다.
- 기존 Personal Memory 카드 UI가 깨지지 않는다.

## Phase 4. Safety, Regression, and Hardening

목표:

- personalization 기능이 기존 memory/agent flow를 깨지 않게 회귀 범위를 봉합한다.
- 악성/부적절 instruction 입력에 대한 최소 안전 장치를 둔다.

태스크:

- [ ] instruction validator가 `approval`, `tool policy`, `system rule override` 성격 입력을 거부하도록 한다.
- [ ] `apps/backend/tests/test_memory_agent_service.py`와 별도의 instruction validator 테스트를 통해 inferred memory와 explicit instruction의 책임 경계를 검증한다.
- [ ] `apps/backend/tests/test_startup.py`에 새 schema patch 호출 개수/순서를 반영한다.
- [ ] settings payload 변경이 기존 auth/settings 화면을 깨지 않는지 관련 프런트 테스트를 확인한다.
- [ ] frontend `npm run build`까지 포함한 최종 회귀 검증을 수행한다.
- [ ] instruction provenance UI는 범위 밖으로 남기되, `personalization_meta`와 trace payload가 후속 작업에 재사용 가능하도록 필드를 남긴다.

검증 기준:

- personalization instruction이 시스템 정책을 덮어쓰지 못한다.
- 기존 chat 응답 경로, memory path, settings shell이 모두 통과한다.
- 후속 단계에서 provenance UI나 temporary mode를 붙일 수 있는 메타데이터가 남아 있다.

## 구현 순서 요약

1. Phase 1에서 schema/API를 먼저 고정한다.
2. Phase 2에서 runtime injection contract를 바꾼다.
3. Phase 3에서 settings UI를 붙인다.
4. Phase 4에서 validator/회귀 검증으로 마감한다.

이 순서를 지켜야 frontend가 미정 API 위에 올라타지 않고, prompt contract도 추측이 아니라 backend canonical schema를 기준으로 정리할 수 있다.
