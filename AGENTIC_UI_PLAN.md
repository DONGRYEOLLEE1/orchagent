# ✨ OrchAgent: Agentic UI Implementation Plan

이 문서는 사용자가 에이전트의 사고 과정(Thought Process)과 도구 호출(Tool Calls)을 실시간으로 관찰할 수 있도록, 세련된 **글래스모피즘(Glassmorphism)** 기반의 UI를 구현하기 위한 계획서입니다.

---

## 🎨 Design Concept: "The Glass Engine"
- **Transparency**: 모든 에이전트 작업 로그는 `backdrop-blur-md`와 반투명 배경(`bg-slate-900/40`)을 사용하여 심미성을 극대화합니다.
- **Micro-Interactions**: 도구 호출 시작 시 테두리에 흐르는 빛 애니메이션(Glowing border)을 적용하여 '살아있는' 느낌을 줍니다.
- **Hierarchical Trace**: Supervisor가 팀을 전환하거나 워커가 도구를 실행할 때 계층 구조를 시각적으로 연결합니다.

---

## 📅 상세 작업 리스트 (TODO)

### Phase 1: Layout Refactoring (공간 분리)
- [ ] **[FE]** 채팅창과 사이드바 비율 조정: 메인 화면 우측에 'Agent Action Space'를 확장 가능한 형태로 배치.
- [ ] **[FE]** 전역 배경 레이어 추가: 글래스모피즘 효과가 돋보일 수 있도록 은은한 그래디언트 배경 적용.

### Phase 2: Tool Execution Monitoring (실시간 도구 시각화)
- [ ] **[FE]** `ToolCard` 컴포넌트 개발:
    - 상태별(Pending, Running, Success, Error) 배지 및 아이콘 적용.
    - 실행 시간(Timer) 표시 및 입출력 데이터 JSON Tree 뷰어 통합.
- [ ] **[FE]** 실시간 이벤트 매핑: 백엔드 `on_tool_start`, `on_tool_end` 이벤트를 가로채어 `ToolCard` 리스트를 실시간 업데이트.

### Phase 3: Thought Process Timeline (사고 추적)
- [ ] **[FE]** `AgentThought` 컴포넌트 개발: 에이전트가 도구를 쓰기 전 '생각(Reasoning)'하는 단계를 별도의 투명 텍스트 박스로 노출.
- [ ] **[FE]** 노드 간 연결선(Flow Line) 구현: Supervisor -> Team -> Worker로 이어지는 흐름을 점선 애니메이션으로 시각화.

### Phase 4: Output Streaming & Polish (응답 정교화)
- [ ] **[FE]** Markdown 렌더링 고도화: AI 답변이 스트리밍될 때 코드 하이라이팅 및 표(Table) 서식의 깨짐 방지.
- [ ] **[FE]** 오토 스크롤 및 포커스: 새로운 도구가 호출될 때 해당 카드로 부드럽게 스크롤 이동.

---

## 🛠️ 기술 스택 및 스타일 가이드 (CSS)

### Glassmorphism 핵심 클래스 (Tailwind)
```css
/* 컴포넌트 기본 스타일 */
.glass-panel {
  @apply backdrop-blur-lg bg-slate-900/40 border border-white/10 shadow-2xl;
}

/* 실행 중인 도구 강조 애니메이션 */
.tool-running {
  box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
  animation: border-glow 2s infinite;
}
```

---

## ✅ 현재 진행 상황 (Status)

| Feature | Assignee | Status |
| :--- | :--- | :--- |
| **Phase 1: Layout** | - | ⏳ 대기 중 |
| **Phase 2: ToolCard** | - | ⏳ 대기 중 |
| **Phase 3: Timeline** | - | ⏳ 대기 중 |
| **Phase 4: Streaming** | - | ⏳ 대기 중 |

*Last Updated: 2026-03-06*
