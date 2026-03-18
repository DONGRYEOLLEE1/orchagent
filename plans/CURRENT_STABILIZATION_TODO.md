# Current Stabilization TODO

본 문서는 최근 디버깅 과정에서 드러난 **아직 미완성인 구현/검증 항목**만 모아둔 단기 TODO 리스트입니다.
우선순위는 사용자가 직접 체감하는 장애, 개발 생산성, 운영 가시성 순으로 정리했습니다.

## 1. Completion Stability

- [ ] `Research Team -> Writing Team -> Finalizer` 경로가 항상 결정적으로 종료되는지 보장
- [ ] 같은 질의가 실행마다 `research_team`으로 되돌아가지 않도록 head routing override 로직 재점검
- [ ] `Writing Team`이 `Doc Writer/Note Taker` 사이에서 불필요하게 왕복하지 않도록 종료 조건 강화
- [ ] `finalizer`가 항상 최종 사용자용 답변 1개만 생성하도록 프롬프트/상태 fallback 보정
- [ ] 장기 질의에서 프론트가 `Completed` 상태와 최종 답변을 안정적으로 받는지 E2E 재검증

## 2. Research Loop Limits

- [ ] `Research Team` dispatch limit이 실제로 **5회 이내**로 강제되는지 fresh thread 기준 재검증
- [ ] `Writing Team` dispatch limit이 실제로 기대한 횟수 내에서 작동하는지 검증
- [ ] 팀별 dispatch counter와 head override 간 상호작용을 테스트 케이스로 추가
- [ ] `GRAPH_RECURSION_LIMIT`와 팀별 dispatch limit의 우선순위/역할 문서화

## 3. Final Answer Channel Separation

- [ ] 답변 박스에는 최종 답변만 나오고, 내부 draft/review/routing 문장은 절대 섞이지 않음을 브라우저 기준으로 재검증
- [ ] `head_supervisor`가 위임 중일 때 `content`를 비우는 정책이 모든 복합 질의에서 지켜지는지 확인
- [ ] 최종 답변이 비어 있을 때 fallback으로 꺼내는 마지막 사용자용 메시지 선택 기준을 더 엄격히 다듬기

## 4. Tool Activity Fidelity

- [ ] 동일 질의에 대해 backend SSE 기준 실제 `tool_start` 횟수를 정확히 계측하고 기준값 확정
- [ ] 프론트 `Tool Activity` 패널이 실제 호출 수보다 적게 보이는 원인 최종 확정
- [ ] 모든 `tool_start` 이벤트가 개별 카드로 누적되는지 브라우저 E2E로 확인
- [ ] `run_id`가 없거나 중복될 때도 카드가 합쳐지지 않도록 매칭 로직 보완
- [ ] Tool Card 토글 UI(기본 접힘, 클릭 시 펼침)가 장기 실행에서도 정상 유지되는지 확인

## 5. Dev Compose / Autoreload

- [ ] `docker compose -f infra/compose/docker-compose.yml up -d --force-recreate`만으로 backend/frontend dev 모드가 깨끗하게 뜨는지 재검증
- [ ] frontend dev container 첫 부팅 시 `npm install --include=dev` 후 `next dev`가 안정적으로 올라오는지 확인
- [ ] backend bind mount + `uvicorn --reload`가 실제 코드 수정 시 자동 재시작되는지 smoke test 유지
- [ ] frontend bind mount + `next dev`가 실제 코드 수정 시 hot reload 되는지 확인
- [ ] `README.md`와 `GEMINI.md`의 dev compose 설명이 실제 운영 방식과 완전히 일치하는지 점검

## 6. Docker Build Hygiene

- [ ] `.dockerignore` 추가/정리로 `node_modules`, `.next`, `.venv`, 로그/캐시가 빌드 컨텍스트에 포함되지 않게 하기
- [ ] dev compose에서는 불필요한 image rebuild 없이도 개발 가능한지 재점검
- [ ] frontend named volume 초기화 전략(`node_modules`, `.next`) 문서화

## 7. Observability

- [ ] backend 로그(`print`, traceback, tool/debug log`)를 프론트 디버그 패널에서 볼 수 있는 최소 UI 설계
- [ ] thread_id 기준으로 backend 로그/trace를 빠르게 추적하는 운영 가이드 정리
- [ ] trace API에 `tool_start/tool_end` 누락 여부 확인 및 필요 시 보강

## 8. Follow-up Validation

- [ ] `"웹검색을 통해 RoPE 알고리즘이 뭔지 500자 내외로 답변해주세요."` 질의에 대해
- [ ] 중간 내부 텍스트는 답변 박스에 나타나지 않고
- [ ] Tool Activity는 실제 호출 수만큼 모두 보이며
- [ ] 최종 답변은 1회만, 자연어로, 완료 상태와 함께 출력되는지 최종 확인
