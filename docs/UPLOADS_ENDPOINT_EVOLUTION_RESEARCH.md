작성일시: 2026-03-28 00:23 KST

# Uploads Endpoint Evolution Research

## 요약

OrchAgent의 업로드 기능은 이미 이미지 전용에서 일반 첨부 구조로 확장됐지만, 프로덕션 수준으로 보려면 아직 `다중 파일 UX`, `재사용 가능한 file_id`, `비동기 전처리`, `출처 확장`, `quota/retention`, `artifact lifecycle` 관점이 더 필요하다.

공식 문서 기준으로 상용 서비스들은 공통적으로 다음 패턴을 가진다.

- 채팅 입력창의 `+` 또는 `Add files`에서 파일을 붙인다
- 한 번에 여러 파일을 붙이는 것을 기본 지원한다
- 장치 업로드뿐 아니라 Drive/OneDrive/Project knowledge base처럼 `지속 참조` 경로를 둔다
- 차트/보고서/문서 같은 `생성 산출물`도 다시 다운로드 가능한 파일로 돌려준다
- 파일 수, 파일 크기, 보존 기간, 학습 사용 여부를 명시한다

이 조사 결과 기준으로 OrchAgent uploads endpoint의 방향은 다음이 적합하다.

- 업로드를 `대화용 일회성 첨부`와 `지속 참조용 파일 자산`으로 분리
- 멀티파일을 1차 시민 기능으로 격상
- 전처리/검사/미리보기/실패 복구를 업로드 수명주기 안에 포함
- Python REPL 산출물까지 동일한 file lifecycle 아래에서 관리

## 상용 서비스 조사

## 1. ChatGPT

OpenAI의 File Uploads FAQ에 따르면 ChatGPT는 대화와 GPT/Project 문맥에서 파일 업로드를 폭넓게 지원한다.

확인 가능한 포인트:

- 공통 문서/스프레드시트/프레젠테이션 계열 파일 지원
- 파일 크기 제한:
  - 일반 파일 512MB
  - 스프레드시트/CSV는 약 50MB
- 업로드 usage cap:
  - 3시간당 최대 80개 파일
- GPT lifetime 기준 10개 파일
- Project 기준 플랜별 20~40개 파일
- 사용량 잔여 quota를 사용자에게 보여주지 않는다고 명시
- Enterprise의 PDF는 visual retrieval 가능

제품적으로 읽히는 포인트:

- 단순 “chat attachment”를 넘어 `project-scoped file container`가 있다
- quota와 retention이 기능 정의의 일부다
- 모든 파일을 같은 방식으로 다루지 않고, 파일 유형별 제한이 다르다

OrchAgent 시사점:

- 업로드 엔드포인트는 파일 타입별 정책을 가져야 한다
- `한 턴 첨부`와 `지속 참조 자산`을 분리하는 설계가 필요하다
- quota를 내부에만 두지 말고 eventually UI에도 노출하는 편이 낫다

## 2. Claude

Claude 공식 도움말과 Files API 문서는 훨씬 직접적인 힌트를 준다.

확인 가능한 포인트:

- chat당 최대 20개 파일
- 파일당 30MB
- `+` 버튼, device upload, drag-and-drop, clipboard paste 지원
- project files는 persistent reference로 사용 가능
- Files API는 `upload once, reuse by file_id` 구조
- code execution tool이 만든 파일을 다시 다운로드 가능
- DOCX/CSV/JSON/XLSX/PDF 등 지원
- XLSX는 code execution/file creation 기능과 연계됨

이건 OrchAgent에 매우 직접적이다.

시사점:

- 현재 `upload -> attachment_id -> one chat turn` 구조만으로는 부족하다
- 재사용 가능한 `file_id` 저장소를 두면 같은 파일을 여러 turn/여러 agent 작업에 다시 붙일 수 있다
- data-science 팀이 만든 PNG, XLSX, DOCX도 “업로드 파일”과 동일한 lifecycle로 다뤄야 한다

즉, Claude는 `input files`와 `generated files`를 같은 제품 표면 위에서 취급한다.

## 3. Gemini

Gemini Apps Help 문서는 다중 파일 UX와 source 확장에서 강한 패턴을 보여준다.

확인 가능한 포인트:

- 같은 prompt에 최대 10개 파일
- 일반 파일은 최대 100MB
- `Add files`
- device upload + Google Drive
- code folder / GitHub repository 추가 가능
- ZIP은 최대 10개 파일 포함 가능
- spreadsheet 기반 chart 생성 가능
- 더 높은 요금제에서 “더 많은 파일”과 “더 많은 chat에서 파일 재참조” 가능

시사점:

- multi-file은 선택 기능이 아니라 기본 기능이다
- source는 로컬 파일만으로 끝나지 않는다
- 단순 file upload 외에 `folder`, `repo`, `zip` 같은 구조적 입력 유형이 확장 포인트다
- 스프레드시트 차트 생성까지 고려하면, 업로드 이후 전처리/preview가 중요하다

## 4. Microsoft Copilot

Microsoft Support 문서는 파일 업로드 기능을 비교적 운영 정책까지 포함해 설명한다.

확인 가능한 포인트:

- 한 conversation에 최대 20개 파일
- 파일 크기 제한 50MB
- 지원 형식:
  - PDF, DOCX, XLSX, PPTX
  - TXT, JSON, CSV, MD
  - 이미지
- 업로드 파일은 최대 18개월 보관
- 업로드 파일은 모델 학습에 사용하지 않는다고 명시
- “Add content to Copilot Chat prompts” 문서에서 `browse my computer` 흐름을 설명
- Microsoft 365 Copilot은 OneDrive/앱 컨텍스트와도 연결됨

시사점:

- retention과 privacy 문구는 제품의 일부다
- 다중 파일 수/크기 제한을 사용자에게 명시해야 한다
- device upload와 cloud source는 별도 but 연결된 UX여야 한다

## 상용 서비스 비교 표

| 서비스 | 다중 파일 | 주요 소스 | 재사용 단위 | 생성 산출물 다운로드 | 눈에 띄는 운영 포인트 |
| --- | --- | --- | --- | --- | --- |
| ChatGPT | 예 | device, project | chat/project | 사실상 가능 | 파일 유형별 크기 제한, 플랜별 프로젝트 파일 수 |
| Claude | 예 | device, drag-drop, clipboard, project files | chat/project/file_id | 예 | Files API, create-once-use-many-times |
| Gemini | 예 | device, Drive, folder, GitHub, zip | prompt/chat | 예 | 10 files/prompt, code repo/folder 지원 |
| Copilot | 예 | device, OneDrive/M365 컨텍스트 | conversation/work context | 예 | 20 files/conversation, 18개월 보관, no training |

## OrchAgent uploads endpoint 고도화 방향

## 1. 업로드 객체를 1차 시민으로 승격

현재 attachment는 “chat turn에 붙는 부속물”에 가깝다. 대규모 단계에서는 업로드 자체를 독립 객체로 다루는 편이 낫다.

최소 메타데이터:

- `file_id`
- `owner_user_id`
- `source_type`
  - `device`
  - `generated_artifact`
  - `drive`
  - `onedrive`
  - `repo`
  - `zip`
- `storage_key`
- `mime_type`
- `declared_extension`
- `sniffed_type`
- `size_bytes`
- `processing_status`
- `preview_status`
- `virus_scan_status`
- `retention_class`

이렇게 해야 chat attachment, project asset, generated artifact를 한 수명주기 안에서 다룰 수 있다.

## 2. 다중 파일은 “배치 업로드” 기준으로 설계

상용 서비스 기준으로 10~20개 동시 업로드는 흔하다. 따라서 backend도 단일 파일 POST 반복이 아니라 batch 중심이 낫다.

좋은 방향:

- 여러 파일을 한 번에 선택
- UI는 per-file progress/status 표시
- 일부 실패 시 부분 성공을 허용하되, 어떤 파일이 실패했는지 명확히 보여줌
- turn submit 시점엔 `attachment_ids[]`만 넘김

핵심은 “업로드”와 “chat 제출”을 분리하는 것이다.

## 3. 비동기 전처리 파이프라인

파일을 받는 순간 끝이 아니라, 이후 단계가 중요하다.

필요한 단계:

- MIME sniffing
- 확장자-실제 타입 불일치 검사
- 악성 파일 스캔
- 문서 텍스트 추출
- 표/시트/컬럼 preview 생성
- 이미지 썸네일 생성
- OCR 필요 여부 판단
- token/size estimation

이걸 synchronous request 안에 다 넣기보다, 업로드 후 `processing_status`를 두고 비동기로 넘기는 편이 낫다.

## 4. “turn 첨부”와 “persistent knowledge file” 분리

ChatGPT Projects, Claude Projects, Copilot Notebook/OneDrive 패턴을 보면 파일은 두 종류로 나뉜다.

- 이번 turn만 참고하는 ephemeral attachment
- 여러 turn/여러 대화에서 다시 참조하는 persistent file

OrchAgent도 결국 이 구분이 필요하다.

예시:

- 사용자가 한 번 업로드한 운영정책 PDF를 다음 turn에서도 다시 참조
- 팀/project 단위로 공통 문서 집합 유지
- memory/personalization과 별개로 “reference corpus”를 유지

## 5. Source 확장

상용 서비스들은 대체로 로컬 업로드에서 끝나지 않는다.

확장 후보:

- local device
- clipboard paste
- drag-and-drop
- Google Drive
- OneDrive
- GitHub repo / code folder
- ZIP

OrchAgent는 현재 단계에선 local device만 있어도 되지만, endpoint 설계는 source 확장을 막지 않는 쪽이 낫다.

즉:

- `POST /uploads`가 로컬 파일 multipart만 가정하지 않도록
- `source_type + source_locator` 구조를 처음부터 염두에 두는 편이 좋다

## 6. Output artifact도 같은 수명주기로 관리

데이터 분석 팀이나 향후 코드/문서 생성 팀은 결과 파일을 계속 만들게 된다.

예:

- PNG 차트
- XLSX 리포트
- DOCX 요약문
- PDF 분석서

이 산출물은 별도 ad-hoc 파일이 아니라 input upload와 같은 체계에 들어가는 것이 낫다.

좋은 방향:

- input file과 output artifact를 동일한 `files` 자산 모델로 관리
- 차이점은 `origin = user_upload | tool_generated`
- 같은 download URL contract
- same retention / delete / permission checks

Claude Files API와 생성 파일 다운로드 패턴이 이 방향과 가깝다.

## 7. Quota, retention, privacy를 제품 계약으로 승격

상용 서비스들은 이 부분을 숨기지 않는다.

필요한 계약:

- 파일당 최대 크기
- prompt당 최대 파일 수
- user/org 총 저장량
- 보존 기간
- 삭제 정책
- 학습 사용 여부
- 사업용/개인용 차등

이건 단순 운영 문서가 아니라 API와 UI에 녹아 있어야 한다.

## 8. Multi-file reasoning 정책

파일을 여러 개 붙이는 순간 모델/에이전트 정책도 필요하다.

최소 계약:

- 파일 간 역할을 구분
  - `주 데이터셋`
  - `보조 데이터셋`
  - `지침 문서`
  - `출력 형식 예시`
- 파일 이름과 타입을 system/user context에 구조적으로 넣기
- 충돌하는 파일이 있으면 우선순위를 명확히 묻기
- 기본적으로는 “전부 참고”가 아니라 “분석에 실제 사용한 파일”을 결과에 명시

즉, 다중 파일 업로드는 UI 문제가 아니라 reasoning contract 문제이기도 하다.

## 9. 운영 측면의 꼭 필요한 메트릭

uploads endpoint를 고도화하면 아래를 반드시 추적해야 한다.

- file type별 성공률
- preprocessing latency
- upload-to-ready latency
- preview generation success rate
- virus scan failure rate
- attachment-to-chat conversion rate
- multi-file prompt usage rate
- generated artifact download rate
- storage usage per user/org

## OrchAgent에 대한 추천 결론

현실적인 우선순위는 이렇다.

1. multi-file을 정식 지원 대상으로 확정
2. upload와 chat submit 분리
3. `file_id` 중심 재사용 구조 도입
4. 비동기 전처리 상태 모델 도입
5. generated artifact를 동일 file lifecycle로 편입
6. source 확장과 project-scoped files는 그 다음 단계

즉, 다음 단계의 uploads endpoint는 단순 multipart POST가 아니라:

- `파일 자산 저장`
- `전처리`
- `재사용`
- `산출물 반환`

을 포함하는 플랫폼 레이어로 가는 편이 맞다.

## 출처

- OpenAI Help: File Uploads FAQ  
  https://help.openai.com/en/articles/8555545-file-uploads-with-chatgpt-and-gpts
- OpenAI Help: What types of files are supported?  
  https://help.openai.com/en/articles/8983675-what-types-of-files-are-supported
- OpenAI Help: Projects in ChatGPT  
  https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt
- Anthropic Help: Uploading files to Claude  
  https://support.claude.com/en/articles/8241126-what-kinds-of-documents-can-i-upload-to-claude
- Anthropic Docs: Files API  
  https://docs.anthropic.com/en/docs/build-with-claude/files
- Anthropic Help: Create and edit files with Claude  
  https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude
- Anthropic Help: What are projects?  
  https://support.claude.com/en/articles/9517075-what-are-projects
- Google Gemini Help: Upload and analyse files in Gemini Apps  
  https://support.google.com/gemini/answer/14903178
- Google Workspace Learning Center: Use the side panel to collaborate with Gemini  
  https://support.google.com/a/users/answer/15146419
- Microsoft Support: File upload in Microsoft Copilot  
  https://support.microsoft.com/en-us/topic/file-upload-in-microsoft-copilot-8b7bf432-9576-4b16-9dee-6c19a4169e62
- Microsoft Support: Add content to Microsoft 365 Copilot Chat prompts  
  https://support.microsoft.com/en-au/topic/add-content-to-microsoft-365-copilot-chat-prompts-438173cf-2a2b-47e0-a1e0-82d830922fe5
- Microsoft Support: File formats supported by Microsoft 365 Copilot  
  https://support.microsoft.com/en-us/topic/file-formats-supported-by-microsoft-365-copilot-1afb9a70-2232-4753-85c2-602c422af3a8
