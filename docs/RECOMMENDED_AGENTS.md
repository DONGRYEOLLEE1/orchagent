# OrchAgent 확장 제안: 추천 에이전트 및 팀 역할 보고서

본 보고서는 최신 멀티 에이전트 프레임워크(LangGraph, CrewAI, AutoGen)의 산업 트렌드 및 유스케이스를 분석하여, 현재 OrchAgent의 아키텍처(Research, Writing, Vision)에 추가하면 시너지를 낼 수 있는 에이전트 역할을 제안합니다.

## 1. 아키텍처 고도화를 위한 필수 에이전트 (Core Architectural Agents)

현재 OrchAgent는 각 팀이 비교적 평면적으로 구성되어 있습니다. 복잡한 문제를 해결하기 위해 다음 역할들을 도입하는 것을 추천합니다.

### 1.1. Planner Agent (기획자/작업 분해자)
*   **역할:** 사용자의 복잡한 요청(예: "우리 회사의 지난 3년 재무 데이터를 분석하고 향후 전략 보고서를 작성해줘")을 받아, 실행 가능한 하위 작업(Sub-tasks)으로 쪼개고 실행 순서(DAG 형태)를 설계합니다.
*   **통합 위치:** `Head Supervisor` 노드 앞단 또는 내부의 초기 계획 수립 단계.
*   **효과:** 에이전트들이 중구난방으로 작업하는 것을 방지하고, 전체적인 목표 달성률을 높입니다.

### 1.2. Reviewer / Critic Agent (검토자/비평가)
*   **역할:** 다른 워커(Worker)나 팀이 생성한 산출물(초안, 코드, 분석 결과)을 비판적으로 검토합니다. 요구사항 누락, 논리적 오류, 할루시네이션(환각)을 찾아내어 피드백과 함께 돌려보냅니다.
*   **통합 위치:** 현재 도입된 `Validator` 노드를 고도화하여 단순 규칙 검사가 아닌 LLM 기반의 심층 비평을 수행하는 전담 에이전트로 격상.
*   **효과:** Reflection(반성) 루프를 통해 결과물의 품질을 엔터프라이즈급으로 끌어올립니다.

---

## 2. 신규 도메인 특화 팀/워커 (Domain-Specific Teams/Workers)

기존 Research, Writing, Vision 외에 실제 비즈니스 유스케이스에서 가장 수요가 많은 역할들입니다.

### 2.1. Data Science & Analytics Team (데이터 분석 팀)
*   **구성원:**
    *   **Data Engineer (데이터 엔지니어):** CSV, SQL DB, JSON 등에서 데이터를 추출하고 전처리합니다. (Pandas/SQL 도구 사용)
    *   **Data Analyst (데이터 분석가):** 통계적 인사이트를 도출하고 시각화 코드를 작성합니다. (Matplotlib, Seaborn 도구 사용)
*   **특징:** AutoGen에서 가장 강력하게 쓰이는 패턴으로, 실제 파이썬 코드를 실행(Python REPL)하여 데이터를 다루는 데 특화되어 있습니다.
*   **유스케이스:** "첨부된 엑셀 파일의 매출 트렌드를 분석해서 차트로 그려줘."

### 2.2. Software Engineering Team (소프트웨어 개발 팀)
*   **구성원:**
    *   **Coder / Developer:** 파이썬, JS 등의 코드를 작성합니다.
    *   **Tester / QA:** Coder가 작성한 코드를 실행하고 버그가 있으면 에러 로그와 함께 Coder에게 수정을 지시합니다.
*   **특징:** LangGraph의 순환(Cycle) 구조를 가장 잘 활용할 수 있는 패턴입니다. 코드가 성공적으로 실행될 때까지 무한 루프를 돌며 자가 수정(Self-correction)을 수행합니다.

### 2.3. Web Operations Team (웹 자동화 팀)
*   **구성원:**
    *   **Browser Navigator:** Selenium이나 Playwright, 혹은 최신 Browser Use 툴을 이용하여 실제 웹 브라우저를 렌더링하고 버튼 클릭, 폼 입력 등을 수행합니다.
    *   **Scraper (기존 기능 강화):** 정적 페이지뿐만 아니라 동적 페이지의 데이터를 긁어옵니다.
*   **유스케이스:** "내일 서울에서 출발하는 제주도 항공권을 검색하고 최저가를 예약해줘."

---

## 3. 추천 구현 로드맵 (Roadmap for OrchAgent)

1.  **단기 (Quick Win): `Data Analyst Worker` 추가**
    *   기존 `WritingTeam`이나 신규 팀에 Python REPL 도구를 쥐여준 Data Analyst 워커를 추가합니다. 이를 통해 OrchAgent가 데이터를 직접 계산하고 차트를 그릴 수 있게 되어 데모 시각화 효과가 뛰어납니다.
2.  **중기 (Architecture Upgrade): `Planner Agent` 도입**
    *   사용자 요청이 들어오면 바로 Research를 할지 Writing을 할지 고르는 대신, Planner가 Markdown 형태의 `Task Plan`을 만들고 이를 `shared_context`에 올려 모든 팀이 공유하며 순차적으로 체크해나가도록 구조를 변경합니다.
3.  **장기 (Expansion): `Browser Operations` 및 외부 API 연동**
    *   이메일 전송, 슬랙 알림, 브라우저 제어 등 외부 세계의 상태를 변경하는(Side-effect) 액션 위주의 에이전트 팀을 구성합니다. 이때 우리가 이전에 구현한 HITL(Human-in-the-Loop) 기능이 빛을 발하게 됩니다.
