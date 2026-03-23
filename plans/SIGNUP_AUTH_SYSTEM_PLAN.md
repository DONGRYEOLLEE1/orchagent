# Signup / Auth System Implementation Plan

작성 시각: 2026-03-23 14:45:00 KST

이 문서는 현재 `anonymous_user` 기반으로 동작하는 OrchAgent에 실제 회원가입/로그인/세션 인증 체계를 도입하기 위한 상세 계획서입니다.
이번 범위는 단순 `POST /signup` 추가가 아니라, 기존 thread ownership, SSE chat/resume, 좌측 thread 목록, 관리자 초기 계정 부트스트랩까지 포함한 인증 시스템 전체를 다룹니다.

중요 전제:

- 현재 코드베이스에는 실사용 가능한 인증이 없다.
- `chat_sessions.user_id` 컬럼은 이미 존재하지만 실제 권한 모델에 연결되어 있지 않다.
- `Base.metadata.create_all()` 기반이라 새 테이블 추가는 가능하지만, 기존 테이블 ALTER 전제 설계는 위험하다.
- 현재 프론트/백은 개발 시 서로 다른 origin(`3000` / `8002`)로 동작할 가능성이 높다.

## 1. 목표

- [ ] 사용자 회원가입/로그인/로그아웃/현재 사용자 조회 기능을 제공한다.
- [ ] 인증된 사용자만 thread 목록, 상세, chat, resume, trace를 사용할 수 있게 만든다.
- [ ] 기존 `anonymous_user`를 제거하고 실제 `user_id`로 session/thread ownership을 연결한다.
- [ ] 초기 관리자 계정 `login_id=admin`, `password=admin1` 을 시드한다.
- [ ] 관리자 초기 계정은 첫 로그인 후 비밀번호 변경을 강제할 수 있도록 설계한다.
- [ ] 쿠키/세션/CSRF까지 포함한 웹 보안 요구사항을 명시적으로 반영한다.
- [ ] 이후 비밀번호 재설정, 이메일 검증, MFA, 관리자 콘솔로 확장 가능한 구조를 만든다.

## 2. 조사 요약

다음 공식/1차 출처를 기준으로 설계 방향을 정한다.

- OWASP Password Storage Cheat Sheet:
  - Argon2id 사용 권장
  - salt는 라이브러리에 맡기되, 필요 시 pepper를 별도 비밀로 관리
- OWASP Authentication Cheat Sheet:
  - 비밀번호는 최소 길이를 강제하고 64자 이상 허용
  - 조합 규칙(대문자/특수문자 강제)은 피하고, 공통/유출 비밀번호 차단을 권장
- OWASP Session Management Cheat Sheet:
  - 인증 상태는 쿠키 기반 세션으로 관리
  - 세션 ID는 예측 불가능해야 하며, 로그인/권한 상승 시 재발급 필요
  - URL 파라미터 세션 전달 금지
- NIST SP 800-63B:
  - 비밀번호는 offline 공격에 저항적인 salted hash로 저장
  - 길이 기반 정책과 blocklist 중심 접근 권장
- FastAPI 공식 보안 튜토리얼:
  - 최신 예제는 `pwdlib` + Argon2 권장

이 계획에서의 핵심 설계 선택은 다음과 같다.

- 추론: 이 서비스는 단일 FastAPI 백엔드와 Postgres를 이미 사용하므로, JWT를 프론트 저장소에 보관하는 방식보다 서버 저장형 opaque session cookie가 더 단순하고 revoke/logout/관리자 제어에 유리하다.
- 추론: cookie 기반 인증을 쓰면 현재 모든 POST API(`/api/chat`, `/api/chat/resume` 포함)에 CSRF 방어가 필요하다.
- 추론: 현재 `allow_credentials=True` 와 `allow_origins=["*"]` 조합은 인증 쿠키 기반 브라우저 요청과 맞지 않으므로, CORS는 명시 origin allowlist로 바꿔야 한다.

## 3. 현재 코드베이스 진단

### 3.1 백엔드

- [x] 사용자 테이블이 없다.
- [x] 인증 라우터가 없다.
- [x] `apps/backend/api/routes/chat.py` 는 `user_id="anonymous_user"` 를 하드코딩한다.
- [x] `apps/backend/services/thread_service.py` 와 `/api/threads` 는 사용자별 필터 없이 전체 thread를 읽는다.
- [x] `apps/backend/models/logging.py` 의 `ChatSession.user_id` 는 nullable string이라, v1에서 실제 사용자 ID를 연결할 수 있는 발판은 있다.
- [x] `apps/backend/main.py` 는 `Base.metadata.create_all()` 만 사용하므로 새 테이블 추가 중심으로 접근해야 한다.
- [x] 현재 CORS 설정은 인증 쿠키 도입에 부적합하다.

### 3.2 프론트엔드

- [x] 현재 메인 UI는 단일 workspace page 위주로 설계되어 있다.
- [x] 로그인/회원가입 페이지, 인증 가드, 현재 사용자 상태 저장소가 없다.
- [x] `src/lib/api.ts` 는 `fetch(..., credentials)` 를 사용하지 않는다.
- [x] 현재 POST 요청은 CSRF 헤더를 보내지 않는다.
- [x] 인증 실패(401/403) 처리와 리다이렉트 정책이 없다.

### 3.3 운영/보안

- [x] `.env.example` 는 추가됐지만 인증 관련 시크릿은 아직 없다.
- [x] 세션 토큰 저장 전략, 토큰 TTL, 강제 로그아웃, 계정 잠금 정책이 없다.
- [x] 로그인/회원가입 rate limit가 없다.
- [x] 비밀번호 정책, 유출 비밀번호 차단, 감사 로그 기준이 없다.

## 4. 권장 범위

### 4.1 이번 v1에 포함할 것

- [ ] username 기반 회원가입
- [ ] 비밀번호 기반 로그인
- [ ] HttpOnly session cookie 기반 인증
- [ ] CSRF 토큰 검증
- [ ] `/api/auth/me` 기반 현재 사용자 조회
- [ ] logout / change-password
- [ ] 관리자 계정 seed
- [ ] 기존 thread/chat/resume/trace 를 사용자 소유권 기반으로 제한
- [ ] 프론트 login/signup/auth-guard

### 4.2 이번 v1에서 제외할 것

- [ ] 이메일 인증
- [ ] 비밀번호 재설정 이메일
- [ ] 소셜 로그인
- [ ] MFA / passkeys
- [ ] 관리자 전용 콘솔 UI
- [ ] 세분화된 권한 정책(RBAC beyond admin/user)
- [ ] 사용자 프로필 편집

## 5. 권장 아키텍처

### 5.1 인증 방식

권장안: `opaque session token + server-side session store + HttpOnly cookie`

이유:

- JWT를 프론트 저장소에 보관할 필요가 없다.
- logout / revoke / password change 시 세션 무효화가 단순하다.
- 관리자 계정/강제 로그아웃/세션 감시가 쉽다.
- 현재 서비스 구조(FastAPI + Postgres 단일 백엔드)에 적합하다.

### 5.2 데이터 모델

권장 신규 테이블:

- [ ] `auth_users`
  - `id`: string UUID
  - `login_id`: unique, indexed
  - `password_hash`
  - `role`: `admin | user`
  - `status`: `active | disabled | pending`
  - `must_change_password`: bool
  - `display_name`: nullable
  - `email`: nullable, unique nullable
  - `last_login_at`: nullable
  - `password_changed_at`: nullable
  - `created_at`
  - `updated_at`
- [ ] `auth_sessions`
  - `id`: string UUID
  - `user_id`
  - `session_token_hash`
  - `csrf_token_hash`
  - `user_agent`
  - `ip_address`
  - `created_at`
  - `last_seen_at`
  - `expires_at`
  - `revoked_at`

v1에서 기존 `chat_sessions.user_id` 는 그대로 활용한다.

- [ ] 신규 auth user가 생성되면 `auth_users.id` 값을 실제 `chat_sessions.user_id` 에 기록
- [ ] `thread_service` 는 항상 현재 인증 사용자 기준으로 filter
- [ ] `/api/thread/{thread_id}/trace` 도 동일 ownership 규칙 적용

### 5.3 비밀번호 저장

- [ ] `pwdlib[argon2]` 또는 동급 Argon2id 지원 라이브러리 채택
- [ ] hash string 안에 알고리즘/파라미터/솔트 버전 정보를 보존
- [ ] 향후 pepper 적용 가능하도록 `AUTH_PASSWORD_PEPPER` 환경변수 확장 지점 마련
- [ ] bootstrap admin 계정도 절대 plaintext 저장 금지

### 5.4 비밀번호 정책

정책 권장안:

- [ ] 일반 사용자 비밀번호 최소 15자
- [ ] 최대 64자 이상 허용
- [ ] Unicode / 공백 허용
- [ ] 소문자 포함 강제
- [ ] 숫자 포함 강제
- [ ] 공통/서비스명 기반 약한 비밀번호 denylist 적용
- [ ] 잘못된 비밀번호여도 username 존재 여부가 timing/메시지로 드러나지 않도록 처리

주의:

- 제품 요구사항 때문에 소문자/숫자 포함 규칙을 적용한다.
- 이 규칙은 회원가입 UI에서 작은 크기 또는 기울임꼴(helper text)로 항상 노출한다.

관리자 bootstrap 예외:

- [ ] 요구사항에 따라 초기 관리자 `admin / admin1` 생성
- [ ] 단, `must_change_password=true` 로 생성
- [ ] 최초 로그인 직후 비밀번호 변경 강제
- [ ] 운영 환경에서는 기본값 사용 시 강한 경고 로그 출력

## 6. 관리자 계정 bootstrap 계획

### 6.1 기본 요구사항

- [ ] startup 시 `ensure_bootstrap_admin()` 실행
- [ ] `login_id=admin` 사용
- [ ] 초기 비밀번호는 `admin1`
- [ ] 계정이 이미 있으면 idempotent no-op
- [ ] 역할은 `admin`
- [ ] `status=active`
- [ ] `must_change_password=true`

### 6.2 권장 환경변수

- [ ] `AUTH_BOOTSTRAP_ADMIN_ENABLED=true`
- [ ] `AUTH_BOOTSTRAP_ADMIN_LOGIN_ID=admin`
- [ ] `AUTH_BOOTSTRAP_ADMIN_PASSWORD=admin1`
- [ ] `AUTH_SESSION_TTL_HOURS=24`
- [ ] `AUTH_SESSION_ABSOLUTE_DAYS=7`
- [ ] `AUTH_ALLOWED_ORIGINS=http://localhost:3000`
- [ ] `AUTH_COOKIE_SECURE=false` (dev) / `true` (prod)

추론:

- 사용자 요구사항 때문에 기본 관리자 자격증명은 명시하되, 코드 상수 하드코딩보다 설정값 기본치로 두는 편이 이후 운영 전환에 안전하다.

## 7. 백엔드 API 권장안

### 7.1 인증 API

- [ ] `POST /api/auth/signup`
  - 입력: `login_id`, `password`, `display_name?`, `email?`
  - 동작: 사용자 생성 + 세션 발급 + cookie 설정
- [ ] `POST /api/auth/login`
  - 입력: `login_id`, `password`
  - 동작: 인증 성공 시 세션 재발급
- [ ] `POST /api/auth/logout`
  - 동작: 현재 세션 revoke
- [ ] `GET /api/auth/me`
  - 출력: `id`, `login_id`, `role`, `display_name`, `must_change_password`
- [ ] `POST /api/auth/change-password`
  - 입력: `current_password`, `new_password`
  - bootstrap admin 첫 로그인 플로우 포함

### 7.2 기존 API 변경

- [ ] `/api/chat`
  - 요청 user context를 session에서 해석
  - `anonymous_user` 제거
- [ ] `/api/chat/resume`
  - 현재 사용자가 해당 thread owner인지 검증
- [ ] `GET /api/threads`
  - 현재 사용자 thread만 반환
- [ ] `GET /api/threads/{thread_id}`
  - owner 아니면 404 또는 403 정책 확정
- [ ] `GET /api/thread/{thread_id}/trace`
  - 동일 ownership 적용

### 7.3 응답/에러 정책

- [ ] signup duplicate: 409
- [ ] invalid credentials: 401 with generic message
- [ ] disabled user: 403
- [ ] not authenticated: 401
- [ ] not owner: 404 또는 403 중 하나로 일관

권장:

- [ ] thread 존재 여부 노출을 줄이기 위해 소유권 불일치는 404 처리

## 8. 세션 / 쿠키 / CSRF 정책

### 8.1 쿠키

- [ ] `HttpOnly`
- [ ] `Secure` prod only
- [ ] `SameSite=Lax`
- [ ] `Path=/`
- [ ] 세션 쿠키 이름은 프레임워크 기본명 대신 일반화된 이름 사용

### 8.2 세션 생명주기

- [ ] 로그인 시 새 세션 발급
- [ ] 비밀번호 변경 시 모든 세션 revoke 또는 최소 현재 외 세션 revoke 정책 결정
- [ ] 로그아웃 시 현재 세션 revoke
- [ ] 관리자 계정 비밀번호 변경 후 bootstrap credential 무효화
- [ ] privilege change(anonymous -> authenticated) 시 세션 재생성

### 8.3 CSRF

cookie 인증을 도입하면 `/api/chat`, `/api/chat/resume` 도 CSRF 보호 대상이다.

- [ ] 로그인 성공 시 HttpOnly session cookie와 별도의 CSRF cookie 발급
- [ ] 프론트는 unsafe method(`POST`, `PUT`, `PATCH`, `DELETE`)에 `X-CSRF-Token` 헤더 전송
- [ ] 백엔드는 cookie/header double-submit 또는 hash 비교 검증
- [ ] `Origin`/`Referer` 검증 추가

## 9. 프론트엔드 권장안

### 9.1 라우팅

- [ ] `app/(auth)/login/page.tsx`
- [ ] `app/(auth)/signup/page.tsx`
- [ ] 기존 workspace `/` 는 인증 필요
- [ ] unauthenticated 사용자는 `/login` 으로 redirect

### 9.2 상태

- [ ] `AuthUser` 타입 추가
- [ ] `auth` 상태 저장소 또는 최상위 provider 추가
- [ ] 앱 시작 시 `/api/auth/me` 조회
- [ ] `must_change_password` 가 true면 workspace 대신 변경 플로우 강제

### 9.3 API 호출층

- [ ] `fetch(..., credentials: 'include')` 적용
- [ ] CSRF header helper 추가
- [ ] 401 공통 처리
- [ ] logout helper 추가

### 9.4 UI/UX

- [ ] signup 폼: `login_id`, `password`, `confirm_password`
- [ ] password strength meter
- [ ] 회원가입 password 입력란 하단에 정책 안내를 작거나 기울임꼴 텍스트로 노출
- [ ] 중복 ID / 약한 비밀번호 / 인증 실패 메시지 분리
- [ ] 관리자 첫 로그인 시 비밀번호 변경 화면
- [ ] workspace 헤더에 현재 사용자/로그아웃 진입점 추가

## 10. 상세 작업 체크리스트

### Phase 0. 설계 고정

- [x] cookie session + CSRF 전략 확정
- [x] `auth_users` / `auth_sessions` 스키마 확정
- [x] 관리자 bootstrap 정책 확정
- [x] ownership 에러 정책(404 vs 403) 확정
- [x] 비밀번호 정책(최소 길이/denylist 범위) 확정

### Phase 1. 모델/설정 추가

- [x] `apps/backend/models/auth.py` 추가
- [x] `apps/backend/models/__init__.py` 등록
- [x] `apps/backend/core/config.py` 에 auth 설정 추가
- [x] startup bootstrap hook 추가
- [x] explicit CORS origin allowlist 도입

### Phase 2. 인증 서비스 계층

- [x] `apps/backend/services/auth_service.py`
  - 사용자 생성
  - password hash/verify
  - session issue/revoke
  - bootstrap admin ensure
- [x] `apps/backend/services/security_service.py`
  - CSRF/쿠키/세션 해석
  - current user dependency
- [x] `apps/backend/services/file_logger.py` 의 `log_user()` 활용 시작

### Phase 3. 인증 API

- [x] `apps/backend/schemas/auth.py`
- [x] `apps/backend/api/routes/auth.py`
- [x] `main.py` router 등록
- [x] signup/login/logout/me/change-password 구현

### Phase 4. 기존 기능과 통합

- [ ] chat route 에 current user dependency 연결
- [ ] resume route ownership 검증
- [ ] thread list/detail/trace user filter 적용
- [ ] `JsonLogger.log_session/log_usage` 에 실제 user_id 반영

### Phase 5. 프론트 auth 도입

- [ ] auth 페이지 구현
- [ ] `/api/auth/me` bootstrap
- [ ] workspace auth guard
- [ ] `credentials: 'include'` 및 CSRF helper 적용
- [ ] logout UI
- [ ] must-change-password UX

### Phase 6. 테스트

- [ ] backend unit tests
  - [ ] password hash/verify
  - [ ] bootstrap admin idempotency
  - [ ] signup duplicate/invalid payload
  - [ ] login success/failure
  - [ ] logout/session revoke
  - [ ] change-password / must-change-password
  - [ ] thread ownership isolation
  - [ ] chat/resume unauthorized/forbidden
- [ ] frontend tests
  - [ ] signup form validation
  - [ ] login redirect
  - [ ] auth guard
  - [ ] logout
  - [ ] must-change-password flow
  - [ ] 401 recovery

### Phase 7. 수동 검증

- [ ] 신규 사용자 회원가입 -> 자동 로그인 -> workspace 진입
- [ ] 로그아웃 -> workspace 접근 차단
- [ ] `admin/admin1` 로그인 -> 즉시 비밀번호 변경 강제
- [ ] 다른 사용자 thread 접근 차단
- [ ] 로그인 후 새 thread 생성 -> 새로고침 후 동일 사용자만 조회 가능
- [ ] CSRF 없이 POST 요청 시 거부

## 11. 리스크 및 주의사항

- [ ] 현재 `create_all()` 기반이라 auth 기능이 커질수록 Alembic 도입 필요성이 커진다.
- [ ] cookie 기반 인증을 도입하면 CORS와 CSRF를 함께 잡아야 한다.
- [ ] `admin/admin1` 기본값은 운영 환경에 그대로 두면 위험하다.
- [ ] 관리자 계정 role을 넣더라도, 관리자 UI/권한 범위는 이번 범위에서 의도적으로 축소해야 한다.
- [ ] 이메일 인증 없이 signup 을 열면 스팸/abuse 리스크가 있다.
- [ ] rate limiting 저장소를 메모리로 두면 multi-instance 환경에서 불완전하다.

## 12. 완료 기준

- [ ] 회원가입/로그인/로그아웃/현재 사용자 조회가 동작한다.
- [ ] 인증되지 않은 사용자는 workspace 와 thread API 를 사용할 수 없다.
- [ ] 사용자별 thread ownership 이 보장된다.
- [ ] 기존 chat/resume/thread/trace 흐름이 실제 사용자 기준으로 회귀 없이 동작한다.
- [ ] 초기 관리자 계정 `admin/admin1` 이 seed 되고, 첫 로그인 후 비밀번호 변경이 강제된다.
- [ ] 프론트가 cookie session + CSRF 정책과 함께 동작한다.

## 13. 구현 순서 권장

1. auth 모델/설정/seed부터 먼저 추가
2. password hashing + session issuance + current user dependency 구축
3. auth API 구현
4. thread/chat/resume ownership 통합
5. 프론트 login/signup/auth guard 연결
6. must-change-password 및 관리자 bootstrap 검증
7. rate limiting / denylist / 운영 hardening 마무리

## 14. 참고 출처

- OWASP Password Storage Cheat Sheet
  - https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP Authentication Cheat Sheet
  - https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet
  - https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- NIST SP 800-63B
  - https://pages.nist.gov/800-63-4/sp800-63b.html
- FastAPI Security Tutorial
  - https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
