작성일시: 2026-03-27 11:27 KST

# Data Science & Analytics Team Research

## 요약

`Data Science & Analytics Team`을 OrchAgent에 넣으려면 단순히 워커 하나를 추가하는 수준으로는 부족하다. 현재 구조는 `image` 첨부와 `vision_team`을 중심으로 설계되어 있고, 데이터 분석 기능이 요구하는 `다중 파일 첨부`, `구조적 데이터 미리보기`, `코드 실행 기반 분석`, `시각화 아티팩트 반환`, `툴 안전장치`가 없다.

웹 조사 기준으로 상용 서비스들은 거의 같은 패턴을 사용한다.

- `첨부 -> 구조 파악 -> 분석/시각화 -> 결과 검증 -> 읽기 쉬운 보고서` 흐름
- 파일은 채팅 입력창의 `+` 또는 `Add content`에서 장치/클라우드 양쪽으로 붙인다
- 모델은 내부적으로 코드 실행 환경을 사용해 통계 계산과 차트 생성을 수행한다
- 차트/테이블/분석 세부 과정은 사용자에게 어느 정도 노출한다
- 파일 종류는 `csv/xlsx/pdf/json/docx` 같은 업무 문서를 우선 지원한다

이 조사 결과를 바탕으로 OrchAgent V1은 다음 방향이 가장 적합하다.

- `data_science_team`을 `research/writing/vision`과 동급의 신규 팀으로 추가
- `Data Engineer`와 `Data Analyst` 두 워커를 두고, 기존 reviewer 루프를 그대로 활용
- 현재의 `images: [base64]` 채팅 API를 `general attachment` 구조로 일반화
- Python REPL은 계속 쓰되, 데이터 분석 전용 래퍼/가드/아티팩트 수집 계층을 얹음
- 파일 파싱은 `DuckDB + pandas`를 축으로 하고, 문서 파싱은 `pypdf + python-docx`로 분리

## 현재 레포 기준 관찰

현재 코드베이스에서 확인한 중요한 제약은 다음과 같다.

- `apps/backend/workflow/main_graph.py`
  - 현재 등록 팀은 `research_team`, `writing_team`, `vision_team`뿐이다.
- `apps/backend/schemas/chat.py`
  - 입력 스키마가 `images: Optional[List[str]]`로 고정돼 있다.
- `apps/backend/api/routes/chat.py`
  - 첨부를 이미지 base64로 받아 바로 멀티모달 메시지와 로컬 파일로 저장한다.
- `apps/backend/services/storage_service.py`
  - 저장소가 이미지 전용이며 파일 형식 추상화가 없다.
- `apps/frontend/src/app/page.tsx`
  - `accept="image/*"` 단일 파일 입력만 있고, 이미지 썸네일 미리보기만 제공한다.
- `apps/frontend/src/types/thread.ts`
  - 첨부 타입이 `kind: 'image'`로 고정돼 있다.
- `packages/agent-tools/src/agent_tools/file_io.py`
  - `python_repl_tool`은 이미 존재하지만, 파일 인입/차트 산출물 추적/보안 가드 없이 범용 도구다.
- `apps/backend/workflow/teams/writing.py`
  - `python_repl_tool`이 `chart_generator`에 붙어 있지만, 데이터 분석 팀이라는 분리된 책임 경계는 없다.

즉, V1 구현의 본질은 `전용 팀 추가`와 동시에 `첨부/툴/아티팩트 파이프라인 일반화`다.

## 웹 조사

### 1. 상용 서비스의 데이터 분석 UX와 동작

#### OpenAI ChatGPT

OpenAI 도움말은 ChatGPT 데이터 분석 기능을 다음처럼 설명한다.

- 업로드된 데이터로 `static + interactive tables/charts`를 생성한다.
- 업로드 후 먼저 몇 행을 살펴 `schema`와 값 타입을 파악한다.
- 내부적으로 `pandas`와 `Matplotlib`를 사용한다.
- 코드 실행 환경에서 코드를 쓰고 실행한 뒤 결과를 응답에 통합한다.
- 한 대화에서 최대 `10`개 파일을 분석할 수 있다.
- 지원 파일 형식에 `xlsx`, `csv`, `pdf`, `json`이 포함된다.

이건 OrchAgent용 데이터 분석 프롬프트에 다음 규칙을 강하게 시사한다.

- 첫 단계는 항상 `파일 구조 파악`이어야 한다.
- 차트는 데이터에 맞는 유형을 선택하되, 사용자가 지정하면 그 지시를 우선한다.
- 분석용 코드는 숨은 내부 scratchpad가 아니라 `재실행 가능하고 저장 가능한 코드`여야 한다.
- 최종 응답은 코드 자체가 아니라 `해석 + 근거 + 차트/표` 중심이어야 한다.

출처:

- [OpenAI Help: Data analysis with ChatGPT](https://help.openai.com/en/articles/8437071-advanced-data-analysis-chatgpt-enterprise-version)

#### Anthropic Claude

Anthropic의 `Data` 플러그인 설명은 데이터 분석 워크플로를 기능 단위로 매우 명확하게 분해한다.

- `/analyze`: ad-hoc data questions
- `/explore-data`: dataset shape / quality profiling
- `/write-query`: SQL generation
- `/create-viz`: Python visualization
- `/build-dashboard`: dashboard creation
- `/validate`: QA before sharing

또한 연결이 없으면 `CSV/Excel` 업로드로 분석할 수 있고, 분석 전에 `profiling`과 `validation` 단계가 별도로 존재한다.

이는 OrchAgent에서도 프롬프트를 “한 번에 다 해라”가 아니라 아래처럼 쪼개야 한다는 뜻이다.

- `Data Engineer`: 파일 구조 파악, 품질 진단, 적재 방식 결정
- `Data Analyst`: 계산, 통계, 차트 생성, 해석
- `Reviewer`: 잘못된 집계/성급한 인과 해석/누락 검증

출처:

- [Anthropic: Data plugin](https://claude.com/plugins/data)
- [Anthropic Docs: Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)

#### Microsoft 365 Copilot Analyst

Microsoft는 아예 `Analyst`라는 전용 에이전트를 제품으로 제공한다.

- `Analyst`를 별도 agent로 노출한다.
- `+ -> Attach content`에서 분석할 파일을 붙인다.
- 장치 업로드와 OneDrive 클라우드 첨부를 둘 다 제공한다.
- `Excel/CSV/DB/other` 다중 파일을 통합 분석 대상으로 상정한다.
- 쉬운 보고서, `charts + tables`, outlier/trend/statistics를 강조한다.

Microsoft의 UX는 OrchAgent 프런트 설계에 직접적인 힌트를 준다.

- 업로드 entry point는 `+` 또는 clip 계열이 맞다.
- 파일은 텍스트 입력창 안쪽보다 `입력창 위의 attachment tray`가 적합하다.
- 장치 업로드와 향후 클라우드 소스 확장을 염두에 둔 메뉴 구조가 적합하다.
- 데이터 분석 팀은 `team`이 아니라 사용자 입장에선 독립된 `agent capability`처럼 보여야 한다.

출처:

- [Microsoft Support: Get started with Analyst in Microsoft 365 Copilot](https://support.microsoft.com/en-gb/topic/get-started-with-analyst-in-microsoft-365-copilot-ff505b9c-a06c-4be9-b855-69d89b1d25d2)
- [Microsoft Support: Add content to Microsoft 365 Copilot Chat prompts](https://support.microsoft.com/en-us/topic/add-content-to-microsoft-365-copilot-chat-prompts-438173cf-2a2b-47e0-a1e0-82d830922fe5)
- [Microsoft Support: File formats supported by Microsoft 365 Copilot](https://support.microsoft.com/en-gb/topic/file-formats-supported-by-microsoft-365-copilot-1afb9a70-2232-4753-85c2-602c422af3a8)
- [Microsoft Support: Turn raw data into dynamic visuals with Microsoft 365 Copilot Pages](https://support.microsoft.com/en-gb/topic/turn-raw-data-into-dynamic-visuals-with-microsoft-365-copilot-pages-8a88637e-87f7-4099-b1c3-1472c2ba625c)

#### Google Gemini

Google는 Gems에 최대 `10`개 파일을 붙이고, 업로드 파일과 Google Drive 최신 버전을 함께 참조하게 한다. 또한 비즈니스용 사전제작 Gem 예시로 `Marketing insights`, `Sentiment analyzer`를 제시한다.

여기서 중요한 시사점은 두 가지다.

- 분석용 agent는 “전문 역할”로 노출될수록 사용성이 좋아진다.
- 파일은 일회성 첨부뿐 아니라 장기적으로 `cloud reference`로 확장할 수 있게 설계하는 편이 좋다.

출처:

- [Google Workspace Blog: Gems with deeper knowledge and business context](https://workspace.google.com/blog/product-announcements/new-gemini-gems-deeper-knowledge-and-business-context)

### 2. 프롬프트/툴 설계 선사례

#### OpenAI

OpenAI 공식 문서는 에이전트 프롬프트에서 다음을 강하게 권한다.

- 역할을 분명히 정의할 것
- 구조화된 tool use 규칙을 줄 것
- 테스트/검증 규칙을 넣을 것
- 함수 이름/파라미터/설명을 매우 구체적으로 쓸 것
- 처음부터 노출하는 함수 수를 너무 늘리지 말 것

이건 데이터 분석 팀에도 그대로 적용된다.

- `Data Engineer`는 “언제 어떤 파서를 써야 하는지”를 구체적으로 명시
- `Data Analyst`는 “언제 Python REPL을 반드시 써야 하는지”를 구체적으로 명시
- 툴 설명 자체에 `when / when not` 규칙을 포함
- V1은 툴 수를 5~8개 안쪽으로 제한

출처:

- [OpenAI Docs: Prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering/)
- [OpenAI Docs: Function calling best practices](https://developers.openai.com/api/docs/guides/function-calling/)
- [OpenAI Cookbook: Multi-agent portfolio collaboration](https://developers.openai.com/cookbook/examples/agents_sdk/multi-agent-portfolio-collaboration/multi_agent_portfolio_collaboration/)

#### Anthropic

Anthropic prompt guide는 아래를 특히 강조한다.

- 툴을 쓰게 하려면 명시적으로 지시할 것
- 툴 결과를 받은 뒤 다음 행동 전에 반성/검토 단계를 둘 것
- 과도한 tool over-trigger를 막기 위해 지시 강도를 적절히 조절할 것

이건 데이터 분석 팀 prompt에서 `inspect -> run -> verify -> summarize`의 4단 구성을 정당화한다.

출처:

- [Anthropic Docs: Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)

### 3. 툴링 후보 조사

#### DuckDB

DuckDB 공식 문서는 다음 점 때문에 데이터 분석 팀의 1차 ingestion 도구로 적합하다.

- CSV를 자동 감지로 바로 읽을 수 있다.
- `read_csv`에 옵션을 주어 delimiter/header/type detection을 제어할 수 있다.
- Excel `.xlsx`를 `read_xlsx`로 읽을 수 있고 sheet/range/header/type inference 제어가 가능하다.

특히 `sheet`와 `range` 지정이 가능해 “시트가 많은 xlsx”나 “헤더가 여러 줄인 파일” 처리에 유리하다.

출처:

- [DuckDB Docs: CSV Import](https://duckdb.org/docs/stable/data/csv/overview)
- [DuckDB Docs: Excel Import](https://duckdb.org/docs/stable/guides/file_formats/excel_import)

#### pypdf

`pypdf`는 텍스트 기반 PDF에서 빠르게 텍스트를 뽑아내는 기본 해법으로 적합하다. 다만 공식 문서가 분명히 말하듯 다음 한계가 있다.

- 스캔본처럼 이미지 기반 PDF는 OCR이 별도로 필요하다
- 표 구조와 whitespace 보존은 어렵다
- 큰 PDF는 메모리 사용량에 주의해야 한다

즉 V1은 `text PDF 우선`, `scanned PDF OCR 비포함`으로 계획하는 편이 현실적이다.

출처:

- [pypdf Docs: Extract Text from a PDF](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)

#### python-docx

`python-docx`는 기존 `.docx`를 열고 내용을 순회하는 기본 도구로 충분하다. 다만 문서 의미 구조를 완벽히 보존하는 parser가 아니라는 점을 전제로 해야 한다.

즉 V1에선 `paragraph/table text extraction` 수준을 목표로 두는 편이 좋다.

출처:

- [python-docx Docs: Quickstart](https://python-docx.readthedocs.io/en/latest/user/quickstart.html)

## 추천 프롬프트 구조

### A. Data Engineer Prompt 원칙

`Data Engineer`는 답변을 멋지게 쓰는 역할이 아니라, 분석 가능한 형태로 문제를 정리하는 역할이어야 한다.

- 먼저 첨부 목록 전체를 확인한다
- 파일별 `kind, mime, size, parse strategy`를 결정한다
- tabular 파일은 행/열/시트/헤더/결측/중복/타입을 먼저 프로파일링한다
- PDF/DOCX는 텍스트 추출 가능 여부와 구조 한계를 먼저 밝힌다
- 불명확한 열 이름, 다중 테이블, 빈 행, 수식 깨짐을 찾아낸다
- `바로 분석`하지 말고 `어떤 데이터가 실제로 쓸 만한지`를 먼저 정리한다

추천 출력 형식:

- `available_files`
- `selected_sources`
- `schema_or_structure`
- `data_quality_risks`
- `recommended_analysis_path`

### B. Data Analyst Prompt 원칙

`Data Analyst`는 Python REPL을 우선 활용하는 계산/시각화 전담이어야 한다.

- 수치 계산, 집계, 통계, 회귀, 시뮬레이션, 시각화가 필요하면 Python REPL을 우선 사용한다
- 임의 계산을 머리로 하지 말고 코드로 검증한다
- 차트는 데이터에 맞는 타입을 택하고, 축/단위/범례를 명확히 적는다
- 차트 파일은 반드시 저장한다
- 최종 답변은 `관찰`, `해석`, `주의점`, `다음 질문`을 분리한다
- 상관관계를 인과로 단정하지 않는다
- 툴 결과가 빈약하거나 에러가 나면 조용히 넘기지 말고 한계를 드러낸다

추천 출력 형식:

- `analysis_goal`
- `steps_run`
- `key_findings`
- `charts_generated`
- `caveats`
- `final_answer_ready`

### C. Reviewer Prompt 원칙

기존 reviewer를 재사용하되 데이터 분석 특화 체크리스트를 추가하는 편이 맞다.

- 잘못된 aggregation
- 잘못된 join/merge
- 표본 수가 너무 작은데 일반화한 경우
- 축/단위/기간 해석 오류
- 결측/이상치 처리 누락
- PDF/DOCX 추출 한계를 무시한 결론

## 추천 툴 세트

V1에서 처음부터 많은 툴을 노출하는 것은 오히려 역효과가 크다. 아래 정도가 적절하다.

1. `inspect_attachments`
- 첨부 목록, mime, size, logical kind, extension 반환

2. `preview_tabular_file`
- csv/xlsx/json의 head, columns, row estimate, sheet list 반환

3. `extract_document_text`
- pdf/docx 텍스트 추출, page/section 단위 metadata 반환

4. `profile_dataframe`
- 결측, distinct count, numeric summary, candidate dimensions/measures 반환

5. `python_repl_data_tool`
- pandas/numpy/matplotlib/seaborn/duckdb가 준비된 분석 전용 REPL
- 생성 파일 목록과 stdout/stderr를 구조화해서 반환

6. `register_analysis_artifact`
- 생성된 png/csv/html를 응답 아티팩트로 등록

V1에서는 `SQL DB connector`, `dashboard builder`, `OCR`, `cloud drives`, `notebook persistence`는 미루는 편이 좋다.

## 파일 업로드 UX 권고

### 필수

- 현재 `Attach image`를 `Add files` 개념으로 확장
- 이미지와 비이미지 파일을 같은 attachment tray에서 보여주기
- 이미지: 썸네일
- 비이미지: 아이콘 + 확장자 badge + 파일명 + 크기
- 지원 형식이 아니면 즉시 클라이언트에서 거부
- 여러 파일 첨부 시 순서를 유지
- 업로드 중 / 준비됨 / 분석에 사용됨 상태를 구분

### 권장

- 메시지 전송 전에도 attachment tray를 보여주기
- 전송 후 user bubble 상단에 첨부 파일을 다시 렌더링
- 차트/산출물도 assistant bubble 하단에 artifact strip으로 노출
- 긴 파일명은 줄이되 hover/full title 제공
- 장기적으로 `device`, `recent`, `cloud` entry point 분리

## OrchAgent에 대한 권고 결론

### 1. 팀 구조

- 신규 `data_science_team` 추가
- 워커는 `data_engineer`, `data_analyst`
- 팀 validator/reviewer는 기존 패턴 재사용

### 2. 라우팅

Head supervisor는 다음 조건이면 `data_science_team`을 우선 고려해야 한다.

- 첨부에 `csv/xlsx/json/pdf/docx`가 있다
- 사용자 질의에 `분석/통계/추세/비교/차트/시각화/회귀/이상치/집계/표` 신호가 있다
- 여러 파일을 함께 비교/통합하라는 지시가 있다

### 3. 업로드 아키텍처

현재 `ChatRequest.images`는 폐기 또는 하위호환으로 두고, 새 canonical path는 `attachment_ids` 또는 `uploaded_files` 참조 구조가 더 적합하다.

이유:

- binary 파일을 매번 JSON base64로 보내는 방식은 PDF/XLSX/DOCX에 비효율적이다
- thread history 재열람, 권한 검증, artifact 재사용에 불리하다
- 향후 cloud file reference 확장과 맞지 않는다

### 4. 코드 실행

Python REPL은 반드시 유지하되, 데이터 분석 전용 wrapper가 필요하다.

- 고정 workspace
- 허용 라이브러리만 preload
- 생성 파일 수집
- 네트워크 금지
- 무제한 파일 I/O 금지
- stdout/stderr 구조화

### 5. 범위 제한

V1은 아래까지로 제한하는 게 맞다.

- `csv`
- `xlsx`
- `json`
- `pdf` 텍스트 기반
- `docx` 텍스트 기반
- `png/jpg/jpeg` 기존 이미지

아래는 V2 이후가 적절하다.

- scanned PDF OCR
- PowerPoint / PPTX
- dashboard HTML embedding
- DB live connector
- cloud pickers
- notebook persistence

## 소스 목록

- [OpenAI Help: Data analysis with ChatGPT](https://help.openai.com/en/articles/8437071-advanced-data-analysis-chatgpt-enterprise-version)
- [Anthropic: Data plugin](https://claude.com/plugins/data)
- [Anthropic Docs: Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Microsoft Support: Get started with Analyst in Microsoft 365 Copilot](https://support.microsoft.com/en-gb/topic/get-started-with-analyst-in-microsoft-365-copilot-ff505b9c-a06c-4be9-b855-69d89b1d25d2)
- [Microsoft Support: Add content to Microsoft 365 Copilot Chat prompts](https://support.microsoft.com/en-us/topic/add-content-to-microsoft-365-copilot-chat-prompts-438173cf-2a2b-47e0-a1e0-82d830922fe5)
- [Microsoft Support: File formats supported by Microsoft 365 Copilot](https://support.microsoft.com/en-gb/topic/file-formats-supported-by-microsoft-365-copilot-1afb9a70-2232-4753-85c2-602c422af3a8)
- [Microsoft Support: Turn raw data into dynamic visuals with Microsoft 365 Copilot Pages](https://support.microsoft.com/en-gb/topic/turn-raw-data-into-dynamic-visuals-with-microsoft-365-copilot-pages-8a88637e-87f7-4099-b1c3-1472c2ba625c)
- [Google Workspace Blog: Gems with deeper knowledge and business context](https://workspace.google.com/blog/product-announcements/new-gemini-gems-deeper-knowledge-and-business-context)
- [OpenAI Docs: Prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering/)
- [OpenAI Docs: Function calling best practices](https://developers.openai.com/api/docs/guides/function-calling/)
- [OpenAI Cookbook: Multi-agent portfolio collaboration](https://developers.openai.com/cookbook/examples/agents_sdk/multi-agent-portfolio-collaboration/multi_agent_portfolio_collaboration/)
- [DuckDB Docs: CSV Import](https://duckdb.org/docs/stable/data/csv/overview)
- [DuckDB Docs: Excel Import](https://duckdb.org/docs/stable/guides/file_formats/excel_import)
- [pypdf Docs: Extract Text from a PDF](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- [python-docx Docs: Quickstart](https://python-docx.readthedocs.io/en/latest/user/quickstart.html)
