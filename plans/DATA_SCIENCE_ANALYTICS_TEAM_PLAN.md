---
작업명: Data Science & Analytics Team Plan
간단요약: 데이터 분석 전용 팀, 일반화된 파일 첨부, Python REPL 기반 시각화 아티팩트 반환을 단계적으로 도입한다.
작성일시: 2026-03-27 11:27 KST
최종 수정일시: 2026-05-21 22:10 KST
---

# Data Science & Analytics Team 기능 추가 및 첨부 리팩토링 계획

## 목표

- `docs/RECOMMENDED_AGENTS.md`의 `2.1 Data Science & Analytics Team`을 실제 런타임 팀으로 구현한다.
- 현재 `image only` 첨부 구조를 `general attachment` 구조로 확장한다.
- 사용자가 `csv/xlsx/json/pdf/docx`를 첨부해 분석을 요청하면, 데이터 분석 팀이 Python REPL 기반으로 계산/시각화/설명을 수행하게 만든다.
- 최우선 목표는 `유저가 파일을 붙이고 자연어로 물으면 차트와 인사이트를 받는 경험`이다.

## 범위

포함:

- backend graph/team/tool/prompt 확장
- general attachment storage/model/API 리팩토링
- frontend compose/upload/history UI 확장
- Python REPL 데이터 분석 wrapper와 아티팩트 반환
- pytest / frontend test / build 검증 계획

비포함:

- scanned PDF OCR
- 외부 DB live connector
- Google Drive / OneDrive picker 실구현
- interactive dashboard HTML 렌더러
- xls / tsv / pptx / parquet 등 추가 포맷의 완전 지원

## 전제

- 프롬프트 문자열은 반드시 `packages/prompt-kit`에서 관리한다.
- worker agent 생성은 `langchain.agents.create_agent`를 유지한다.
- 기존 `vision_team` 경로와 이미지 첨부 UX는 깨지면 안 된다.
- 기존 thread attachment/history 조회 경로는 재사용하되, attachment kind를 일반화한다.
- V1 지원 포맷은 `image`, `pdf`, `xlsx`, `csv`, `json`, `docx`다.

## 설계 결론

### 1. 팀 구조

- 신규 `data_science_team` 추가
- 워커:
  - `data_engineer`
  - `data_analyst`
- reviewer:
  - 기존 reviewer/validator 루프 재사용

### 2. prompt engineering 방향

- `Data Engineer`
  - 첨부 구조 파악, schema/profile, data quality risk 식별
  - 즉시 해석하지 말고 “분석 가능한 기반”을 만드는 역할
- `Data Analyst`
  - Python REPL을 우선 사용해 수치 계산과 시각화 수행
  - 최종 답변은 `관찰 / 해석 / caveat` 분리
- `Reviewer`
  - 잘못된 집계, 누락된 결측 처리, 과도한 일반화, 잘못된 chart labeling 검증

### 3. 첨부 아키텍처

현재 `ChatRequest.images` 경로는 유지 호환만 하고, canonical path는 아래로 옮긴다.

- `multipart upload -> uploaded file metadata -> chat request는 attachment ids 참조`

이유:

- PDF/XLSX/DOCX를 JSON base64로 보내는 건 비효율적이다.
- 업로드와 메시지 전송을 분리해야 retry/history/reuse가 쉬워진다.
- assistant artifact와 user attachment를 같은 attachment model로 묶기 쉽다.

### 4. 데이터 분석 툴 세트

V1에서 처음 노출할 툴은 작게 유지한다.

- `inspect_attachments`
- `preview_tabular_file`
- `extract_document_text`
- `profile_dataframe`
- `python_repl_data_tool`
- `register_analysis_artifact`

### 5. 파싱 전략

- `csv`
  - DuckDB `read_csv` 또는 pandas
- `xlsx`
  - DuckDB `read_xlsx` 우선, sheet/range metadata 활용
- `json`
  - pandas / Python stdlib
- `pdf`
  - pypdf text extraction, scanned PDF는 unsupported 또는 partial
- `docx`
  - python-docx paragraph/table text extraction

### 6. 프런트 UX 방향

- 입력창 좌측 버튼을 `Attach image`에서 `Add files` 개념으로 확장
- 이미지/문서/스프레드시트/JSON을 같은 tray에 표시
- 이미지: thumbnail
- 비이미지: icon + extension badge + filename + size + remove
- 전송 후 user bubble 상단에도 attachment strip 표시
- assistant가 생성한 차트는 artifact strip 또는 inline card로 표시

## 검증 기준

- 사용자가 `xlsx/csv/json/pdf/docx/image`를 첨부할 수 있다.
- `data_science_team`이 supervisor 라우팅에 실제로 들어간다.
- Python REPL이 생성한 차트 파일이 사용자에게 보인다.
- thread history 재조회 시 첨부와 생성 아티팩트가 유지된다.
- 분석 불가능 파일 또는 scanned PDF는 실패를 숨기지 않고 명확히 고지한다.

## Phase 1. Attachment 모델 일반화

- [x] 현재 image 전용 흐름과 attachment 관련 타입/스키마 전체 매핑 작성
- [x] `ChatRequest.images`와 별개로 일반 attachment용 업로드/전송 계약 초안 작성
- [x] backend에 `uploaded_files` 또는 동등한 canonical metadata 모델 추가
- [x] attachment kind enum을 `image | pdf | spreadsheet | csv | json | docx | artifact` 수준으로 일반화
- [x] storage service를 이미지 전용에서 파일 일반 저장소로 리팩토링
- [x] thread detail / attachment serving API가 일반 파일 kind를 반환하도록 변경
- [x] 관련 schema/type 갱신
- [x] 관련 pytest 추가 및 통과 확인

## Phase 2. Frontend 파일 추가 UX

- [x] compose area의 첨부 진입점을 `Add files`로 전환
- [x] `accept`를 이미지 + pdf + xlsx + csv + json + docx로 확장
- [x] 클라이언트에서 확장자/mime 선검증 추가
- [x] 이미지 thumbnail + 문서 file chip 혼합 preview tray 구현
- [x] 업로드 중 / 준비됨 / 실패 상태를 tray에 표시
- [x] 전송 payload를 attachment id 참조 구조로 전환
- [x] user bubble 상단 attachment strip을 일반 파일용으로 확장
- [x] thread reopen 시 attachment strip이 일관되게 복원되도록 수정
- [x] 프런트 관련 테스트 추가 및 통과 확인
- [x] `npm run lint`
- [x] `npm run build`

## Phase 3. 데이터 분석 전용 툴 추가

- [x] `agent-tools`에 `inspect_attachments` 추가
- [x] `agent-tools`에 `preview_tabular_file` 추가
- [x] `agent-tools`에 `extract_document_text` 추가
- [x] `agent-tools`에 `profile_dataframe` 추가
- [x] 기존 `python_repl_tool`을 감싼 `python_repl_data_tool` 설계
- [x] 분석용 REPL workspace, artifact directory, generated files collection 추가
- [x] 허용 라이브러리 preload 규칙 정의
- [x] 네트워크 사용 금지, 외부 경로 접근 제한, 파일 수 제한 등 안전장치 추가
- [x] assistant artifact 등록용 helper/tool 추가
- [x] 관련 pytest 추가 및 통과 확인

## Phase 4. Prompt Kit 확장

- [x] `prompt-kit`에 `DATA_ENGINEER_PROMPT` 추가
- [x] `prompt-kit`에 `DATA_ANALYST_PROMPT` 추가
- [x] reviewer가 데이터 분석 산출물을 검토할 때의 평가 기준 문구 보강
- [x] tool descriptions에 `when / when not` 규칙 추가
- [x] prompt에 `inspect -> profile -> analyze -> validate -> answer` 흐름 반영
- [x] prompt에 `Python REPL must be used for material calculations or charts` 규칙 반영
- [x] prompt에 `observations / interpretation / caveats` 출력 구조 반영
- [x] prompt 관련 테스트 또는 회귀 검증 추가

## Phase 5. Data Science Team 런타임 도입

- [x] `apps/backend/workflow/teams/data_science.py` 추가
- [x] `TeamBuilder` 기반으로 `data_engineer`, `data_analyst` worker 구성
- [x] `main_graph.py`에 `data_science_team` 등록
- [x] head supervisor team 목록에 `data_science_team` 추가
- [x] 첨부 종류와 질의 의도를 기준으로 한 data-science 라우팅 규칙 추가
- [x] 기존 `vision_team` 강제 라우팅과 충돌하지 않도록 우선순위 규칙 설계
- [x] reviewer loop가 데이터 분석 팀에도 정상 적용되는지 검증
- [x] 관련 pytest 추가 및 통과 확인

## Phase 6. 아티팩트 반환 및 응답 통합

- [x] Python REPL 산출물 png/csv/html 메타데이터를 assistant attachment/artifact로 저장
- [x] finalizer가 artifacts 정보를 읽어 최종 응답에 자연스럽게 통합하도록 조정
- [x] assistant bubble 하단 artifact renderer 추가
- [x] 차트 이미지와 다운로드 링크 노출 방식 결정 및 구현
- [x] 실패한 artifact 생성 시 fallback 메시지 규칙 추가
- [x] 관련 프런트/백엔드 테스트 추가 및 통과 확인

## Phase 7. 데이터 분석 품질 및 안전성 검증

- [x] csv 매출 추세 분석 시나리오 수동/자동 검증
- [x] xlsx 다중 시트 선택/집계 시나리오 검증
- [x] json 구조 분석 및 chart 생성 시나리오 검증
- [x] text PDF 요약/표현 가능 범위 검증
- [x] scanned PDF 입력 시 partial/unsupported 응답 검증
- [x] docx 텍스트 추출 및 요약 시나리오 검증
- [x] 다중 파일 비교 분석 시나리오 검증 — S-D `sales.csv + metrics.csv` 두 파일 동시 첨부 → 두 서브플롯 PNG(`sales_region_revenue_and_monthly_mrr.png`) 생성 + 다운로드 링크 노출 확인 (dong 계정, playwright)
- [x] 잘못된 aggregation을 reviewer가 되돌리는 회귀 테스트 검증
- [x] unsupported mime / corrupt file 처리 검증 — S-F1 `binary_blob.bin` 첨부 시 frontend client-side mime validation으로 즉시 tray 진입 거부(silent reject) 정상 작동. S-F2 `corrupt.pdf`(PDF header 없는 깨진 파일) 첨부 시 LLM이 "파일이 깨져있거나 텍스트 레이어가 없음, OCR 필요"라고 사용자에게 명확히 고지 + 정상 PDF 재첨부/텍스트 직접 붙여넣기 등 구체적 대안 제안. 실패를 숨기지 않음 — plan §"검증 기준" 4번 충족. oversized file 케이스는 frontend `validateIncomingDraftFiles`가 kind별 byte limit(10MB CSV / 30MB total)으로 사전 거부 — 회귀 검증 외 신규 변경 0.
- [x] 성능 관점에서 large spreadsheet preview/analysis p95 측정

## Phase 8. 출시 전 마감 조건

- [x] backend 관련 pytest 통과
- [x] frontend 관련 테스트 통과
- [x] `npm run lint` 통과
- [x] `npm run build` 통과
- [x] 브라우저 수동 E2E:
  - [x] csv 업로드 후 추세 차트 확인
  - [x] xlsx 업로드 후 sheet 기반 분석 확인
  - [x] pdf/docx 업로드 후 텍스트 기반 분석 확인
  - [x] assistant artifact 재조회 확인
- [x] docs와 plan 체크리스트 최신화

## 구현 순서 메모

권장 구현 순서는 다음이다.

1. Attachment substrate
2. Frontend upload UX
3. Tooling and safe REPL
4. Prompt kit
5. Team wiring and routing
6. Artifact rendering
7. QA / performance hardening

이 순서를 어기면, 데이터 분석 팀 prompt를 먼저 만들어도 실제로는 첨부와 툴이 없어 검증이 불가능해진다.

## 2026-05-21 후속 검증 결과 (dong 계정, playwright MCP E2E)

본 plan의 시각화 + 다운로드 기능이 일관되게 실패하던 회귀를 prompt 강화 + matplotlib robustness만으로 복구. 룰 베이스 추가 없음 (CLAUDE.md §"Supervisor → Sub-agent Handoff 정책" P1~P5 준수).

### 시나리오 (6/6 PASS)

| ID | 입력 | 결과 |
| :--- | :--- | :--- |
| S-A | trend.csv 시계열 라인차트 | ✅ `trend_revenue.png` + 다운로드 |
| S-B | products.json category 막대차트 | ✅ `category_avg_price_bar.png` + 다운로드 |
| S-C | multi_sheet.xlsx sales/costs 비교 | ✅ `revenue_vs_cost_bar.png` + 다운로드 |
| S-D | sales.csv + metrics.csv 다중 서브플롯 | ✅ `sales_region_revenue_and_monthly_mrr.png` + 다운로드 |
| S-E | korean_sales.csv 한국어 라벨 막대차트 | ✅ `korean_sales_by_region.png` + 다운로드 (CJK font + savefig 재시도) |
| S-F | binary_blob.bin / corrupt.pdf 실패 케이스 | ✅ frontend silent reject / LLM이 "파일 깨졌음, OCR 필요" 명확 고지 |

### 머지된 fix (3 PR)

- **PR #10** `ae261ad` — DATA_ENGINEER/ANALYST/TEAM_SUPERVISOR/SYSTEM_SUPERVISOR/REVIEWER prompt 강화 + `python_repl_data_tool` `plt.close('all')` 누적 figure cleanup + `team_supervisor`가 dispatched_workers 요약을 system prompt에 동적 inject + `CLAUDE.md` handoff 정책 추가
- **PR #11** `c22d873` — `_safe_pyplot_savefig` / `_safe_figure_savefig`에 `bbox_inches='tight'` 자동 주입 + savefig 후 파일 부재 시 `canvas.draw()` retry (S-E 한글 silent fail 해소)
- **PR #14** `d3ddf77` — 멀티 turn follow-up 5종 fix: LLMRouter parse-failure retry+salvage, head/team supervisor의 current-turn-only redirect/dispatch 카운트, worker history note prev/current 분리, finalizer 경유 head도 turn 종료 status="completed" 마킹, matplotlib savefig monkey-patch nesting 차단

### data_engineer 첫 분기 보장 — 다층 검증 (2026-05-22)

본 session에서 `data_engineer`가 데이터 첨부 turn의 **첫 worker**로 확실히 분기되는지 다음 4층으로 검증·강화:

1. **SYSTEM_SUPERVISOR_PROMPT** `# TEAM SELECTION HINTS`: 데이터 첨부(csv/xlsx/json/pdf/docx)는 **MUST `data_science_team`** 명시
2. **TEAM_SUPERVISOR_PROMPT** `# DATA SCIENCE TEAM HANDOFF`: `data_engineer`가 ONE-pass inspection만 수행, 그 후 ALWAYS `data_analyst` 강제 가이드 명시
3. **routing_eval/golden_dataset.json**: data_science 카테고리 7 케이스(`data-001`~`data-007`) 모두 `expected_next: data_science_team` — scorer가 회귀 시 즉시 감지
4. **routing_eval `data_engineer_first` 보강 케이스** (본 session 추가): team-layer router가 첫 dispatch에서 `data_engineer`를 선택하는지 확인하는 단위 평가

회귀: pytest 184/184 PASS (2차 축소 후), vitest 54/54 PASS, build PASS, CI 통과.

## 참고 문서

- `docs/RECOMMENDED_AGENTS.md`
- `docs/DATA_SCIENCE_ANALYTICS_TEAM_RESEARCH.md`
- `CLAUDE.md` §"Supervisor → Sub-agent Handoff 정책" (룰 베이스 금지 명문화)
