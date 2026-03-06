# 🖼️ OrchAgent Multimodal Expansion Plan

이 문서는 기존 텍스트 기반 계층형 에이전트 시스템(OrchAgent)을 **이미지 분석(VLM)이 가능한 멀티모달 파이프라인**으로 확장하기 위한 상세 작업 일지 및 TODO 리스트입니다.

---

## 🎯 목표 (Goal)
- 사용자가 텍스트와 함께 이미지를 첨부하여 요청할 수 있는 프론트엔드 환경 구축
- 백엔드에서 이미지(Base64 또는 URL)를 수신하고 LangGraph의 상태(State)에 올바르게 병합
- 시각 데이터를 전문적으로 처리하는 `Vision Team` 및 전용 프롬프트 신설
- 무거운 이미지 데이터를 DB에 직접 넣지 않고 외부 스토리지(또는 로컬 폴더)에 저장 후 링크만 로깅하는 아키텍처 적용

---

## 📅 상세 작업 일지 (Milestones)

### Phase 1: Data Ingestion (API & 클라이언트 확장)
- [ ] **[FE]** UI 업데이트: 채팅 입력창에 이미지 첨부(파일 선택 및 Drag & Drop) 버튼/영역 추가
- [ ] **[FE]** 데이터 처리: 업로드된 이미지를 `Base64` 문자열로 인코딩하여 전송 로직 구현
- [ ] **[BE]** 스키마 업데이트: `apps/backend/schemas/chat.py`의 `ChatRequest`에 `images: List[str]` 필드(선택적) 추가
- [ ] **[BE]** 상태 메시지 변환: `api/routes/chat.py`에서 전달받은 `images` 배열을 LangChain 규격의 멀티모달 `HumanMessage` (`[{"type": "text", ...}, {"type": "image_url", ...}]`) 형태로 변환

### Phase 2: Orchestration (라우팅 및 State 호환성 보장)
- [ ] **[BE]** State 호환성 확인: `agent_core/state.py`의 `BaseAgentState`가 리스트 딕셔너리 형태의 `HumanMessage`를 제대로 처리하는지 검증
- [ ] **[BE]** Head Supervisor 프롬프트 수정: 이미지 관련 요청이 들어왔을 때 이를 분석할 수 있는 `vision_team`으로 정확히 라우팅하도록 규칙 추가

### Phase 3: Vision Team & Tools (시각 지능 에이전트 구현)
- [ ] **[BE/Prompt]** 프롬프트 추가: `prompt-kit`에 VLM 전문 분석가 역할을 수행하는 `VISION_ANALYST_PROMPT` 작성
- [ ] **[BE]** 신규 도구 개발: `agent_tools/vision.py`를 생성하여 이미지 크롭, 메타데이터 추출, 필요시 외부 OCR API 호출 도구 등을 구현
- [ ] **[BE]** Vision Team 서브그래프: `apps/backend/workflow/teams/vision.py` 생성 및 `vision_analyst` 워커 등록
- [ ] **[BE]** 메인 그래프 통합: `main_graph.py`에 `vision_team` 서브그래프를 연결하고 라우팅 대상에 포함

### Phase 4: Storage & Logging (성능 최적화 및 로깅)
- [ ] **[BE]** 스토리지 관리: Base64로 들어온 이미지를 디스크(예: `apps/backend/data/images/`)에 임시 파일로 저장하고 URL 매핑 로직 구현
- [ ] **[BE]** 로깅 최적화: `models/logging.py` 및 `JsonLogger`가 메가바이트 단위의 Base64 텍스트를 그대로 저장하지 않고, 파싱하여 "이미지 포함 (URL: ...)" 형태의 메타데이터만 남기도록 방어 코드 추가

---

## ✅ 현재 진행 상황 (Status)

| Task | Assignee | Status |
| :--- | :--- | :--- |
| **Phase 1** | - | ⏳ 대기 중 (Pending) |
| **Phase 2** | - | ⏳ 대기 중 (Pending) |
| **Phase 3** | - | ⏳ 대기 중 (Pending) |
| **Phase 4** | - | ⏳ 대기 중 (Pending) |

*Last Updated: 2026-03-06*
