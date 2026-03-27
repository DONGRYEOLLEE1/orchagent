---
작업명: Uploads Endpoint Evolution Plan
간단요약: 업로드 기능을 프로덕션 지향 구조로 고도화하되, V1 운영 한도를 `최대 5개 파일`, `파일당 10~20MB`, `요청 총합 30MB`로 고정한다.
작성일시: 2026-03-28 00:41 KST
최종 수정일시: 2026-03-28 01:18 KST
---

# Uploads Endpoint Evolution Plan

## 목표

- 현재 general attachment 업로드 기능을 프로덕션 운영을 버틸 수 있는 구조로 고도화한다.
- 다중 파일 업로드를 정식 지원하되, 초기 운영 한도를 명확히 고정한다.
- 업로드를 단순 multipart POST가 아니라 `파일 자산 저장 -> 전처리 -> 재사용 -> 산출물 반환`을 포함하는 플랫폼 레이어로 정리한다.

## V1 정책 결정

이번 플랜에서 우선 고정하는 운영 값은 다음과 같다.

### 다중 파일 수

- 한 번의 chat turn에서 최대 `5개` 파일

### 파일당 최대 크기

- `pdf`: `20MB`
- `docx`: `20MB`
- `xlsx`: `20MB`
- `json`: `20MB`
- `csv`: `10MB`
- `image/*`: `10MB`

### 요청 총합 최대 크기

- 한 번의 chat turn에서 업로드되는 파일 총합은 최대 `30MB`

## 왜 이 값으로 시작하는가

- 상용 서비스는 10~20개 파일까지도 허용하지만, OrchAgent는 현재 업로드 후 전처리, 파싱, 분석, Python REPL, artifact 생성까지 이어진다.
- 따라서 병목은 업로드 순간보다 후속 처리에 있다.
- 특히 `csv/xlsx/pdf/docx`는 파일 크기보다도 `행 수`, `시트 수`, `추출 텍스트 길이`, `토큰량`이 비용을 키운다.
- V1은 상용 서비스 최대치보다 보수적으로 시작하고, 실제 운영 지표를 본 뒤 완화하는 편이 안전하다.

## 범위

포함:

- 업로드 수/크기 정책 서버 강제
- 프런트 업로드 UX에 정책 반영
- 배치 업로드 흐름 정리
- 전처리 상태 모델 초안 도입
- 생성 artifact와 입력 파일 lifecycle 정리
- 운영 지표/오류 코드 계약 정리

비포함:

- Google Drive / OneDrive / GitHub / ZIP 연동
- 조직 단위 quota/과금 체계
- 장기 보관 프로젝트 파일 기능

## 최종 방향

V1 이후 업로드 계층은 아래 구조를 목표로 한다.

- `업로드 파일 자산`
  - user upload
  - generated artifact
- `turn attachment 참조`
  - chat turn별 attachment_ids 연결
- `전처리 상태`
  - mime sniffing
  - preview generation
  - text extraction
  - scan/validation
- `재사용성`
  - file_id 기준으로 같은 파일 재참조 가능

즉, 단순 “현재 turn에 붙는 파일”이 아니라 `파일 자산 레이어 + turn 연결 레이어`로 나누는 것이 목표다.

## 전제

- 현재는 local device upload만 고려한다.
- 현재 지원 확장자는 `pdf`, `xlsx`, `csv`, `json`, `docx`, `image/*`다.
- data-science 팀이 생성한 PNG/XLSX/DOCX/PDF도 장기적으로는 동일한 file lifecycle 아래에서 관리한다.

## 검증 기준

- 서버가 정책을 초과하는 파일 개수/크기를 일관되게 차단한다.
- 프런트가 선택 단계에서 파일 개수/크기 오류를 즉시 보여준다.
- 부분 업로드 실패가 어떤 파일 때문인지 식별 가능하다.
- 차트/보고서 같은 생성 artifact도 동일한 download contract를 유지한다.

## Phase 1. 정책 고정 및 서버 검증

- [x] 허용 파일 수 `5개` 제한을 서버 상수로 고정
- [x] 파일 타입별 최대 크기 제한을 서버 검증으로 고정
- [x] 요청 총합 `30MB` 제한을 서버 검증으로 고정
- [x] 초과 시 일관된 에러 코드/메시지 계약 정의
- [x] 관련 테스트 추가 및 통과 확인

## Phase 2. 프런트 업로드 UX 보강

- [x] 파일 선택 직후 `최대 5개` 정책을 즉시 검증
- [x] 파일별 크기 초과를 업로드 전 단계에서 즉시 노출
- [x] 총합 `30MB` 초과를 즉시 노출
- [x] 다중 파일 선택 시 per-file 상태가 보이도록 개선
- [x] 관련 테스트 추가 및 통과 확인

## Phase 3. 배치 업로드 흐름 정리

- [x] 업로드와 chat submit 흐름을 더 명확히 분리
- [x] 다중 파일에서 부분 성공/부분 실패 처리 정책 정리
- [x] 프런트가 업로드 완료 파일만 `attachment_ids[]`로 넘기도록 정리
- [x] 실패 파일 재시도 UX 가능성 검토
- [x] 관련 테스트 추가 및 통과 확인

## Phase 4. 파일 자산 모델 확장

- [x] `file_id` 중심 자산 모델 보강
- [x] `source_type` 구분
  - [x] `device`
  - [x] `generated_artifact`
- [x] `processing_status`, `preview_status` 같은 상태 필드 초안 도입
- [x] turn attachment와 file asset의 책임 경계 정리
- [x] 관련 테스트 추가 및 통과 확인

## Phase 5. 비동기 전처리 파이프라인 초안

- [x] MIME sniffing / 확장자-실제 타입 불일치 검사 추가
- [x] 문서/표 preview 생성 지점 정리
- [x] 이미지 썸네일 생성 지점 정리
- [ ] OCR / text extraction / token estimate를 비동기 단계로 넘길 기준 정의
- [x] 전처리 실패가 chat 전체 실패로 번지지 않도록 실패 분리 정책 정리

## Phase 6. 생성 artifact lifecycle 정리

- [x] data-science 팀 산출물을 `generated_artifact`로 표준화
- [x] 입력 파일과 같은 download contract 유지
- [x] artifact 메타데이터를 동일 file lifecycle로 수렴
- [ ] retention/delete 권한 정책 초안 정리
- [x] 관련 테스트 추가 및 통과 확인

## Phase 7. 운영 지표와 안정화

- [ ] file type별 업로드 성공률 지표 정의
- [ ] upload-to-ready latency 지표 정의
- [ ] preview/text extraction 성공률 지표 정의
- [ ] multi-file 사용률 지표 정의
- [ ] generated artifact download rate 지표 정의
- [ ] user별 storage usage / quota 지표 정의

## Phase 8. 출시 전 검증

- [x] `npm run test`
- [x] 백엔드 관련 `pytest` 통과
- [x] `npm run lint`
- [x] `npm run build`
- [ ] 수동 검증
  - [x] 5개까지 업로드 가능 확인
  - [x] 6개 선택 시 즉시 차단 확인
  - [ ] 파일당 크기 초과 차단 확인
  - [ ] 총합 30MB 초과 차단 확인
  - [x] 다중 파일 등록 -> 관련 질의 -> 예상된 답변 나타나는지 확인
  - [ ] 다중 파일 부분 실패 처리 확인
  - [ ] 생성 artifact download contract 확인

## 구현 원칙

- 초기 운영값은 보수적으로 시작하고, 지표를 본 뒤 완화한다.
- 파일 수 제한보다 중요한 것은 후속 처리 비용이므로, type별 제한과 총합 제한을 함께 둔다.
- 입력 파일과 생성 artifact를 서로 다른 ad-hoc 시스템으로 두지 않는다.
- upload endpoint는 장기적으로 `device upload` 외 source 확장을 막지 않는 구조여야 한다.
