# PATCH Endpoint Evolution Plan

작성 시각: 2026-03-23 16:07:57 KST

이 문서는 OrchAgent에서 향후 부분 수정(partial update) 기능을 자연스럽게 확장하기 위해 `PATCH` 메서드를 도입/확장하는 계획서입니다.
범위는 두 가지입니다.

1. 기존 `POST` 엔드포인트 중 `PATCH`로 바꾸면 안 되는 것과 바꿔도 되는 후보를 구분한다.
2. 실제로 개발 가치가 높은 `PATCH` 엔드포인트 3개를 백엔드+프론트 연동 기준으로 상세 설계한다.

중요 전제:

- 현재 인증 체계와 thread ownership은 이미 도입되어 있다.
- 현재 DB는 여전히 `Base.metadata.create_all()` 중심이라, 기존 테이블 ALTER 전제 설계는 위험하다.
- `thread rename / pin`은 이미 [THREAD_HISTORY_SIDEBAR_REFACTOR_PLAN.md](/Users/drlee/workspace/orchagent/plans/THREAD_HISTORY_SIDEBAR_REFACTOR_PLAN.md)에 후속 기능으로 언급되어 있다.
- 사용자 프로필 수정은 이미 [SIGNUP_AUTH_SYSTEM_PLAN.md](/Users/drlee/workspace/orchagent/plans/SIGNUP_AUTH_SYSTEM_PLAN.md)의 후속 auth 확장선에 있다.

## 1. 목표

- [ ] 기존 HTTP 메서드 사용을 resource semantics 기준으로 정리한다.
- [ ] `PATCH`가 실제로 적합한 3개 엔드포인트를 정의한다.
- [ ] thread rename / pin / archive 와 사용자 프로필 수정, 관리자 상태 변경을 자연스럽게 붙일 수 있게 만든다.
- [ ] 프론트에서 낙관적 업데이트와 권한/ownership/validation 처리를 함께 고려한다.
- [ ] 기존 `POST` 엔드포인트와의 호환성 및 문서화 전략을 정리한다.

## 2. 조사 요약

`PATCH`와 `PUT`은 다음 기준으로 구분한다.

- MDN / RFC 5789 기준:
  - `PATCH`는 partial modifications
  - `PUT`은 전체 표현(representation) 교체에 더 가깝다
- 추론:
  - 우리 프로젝트는 기존 리소스에 대해 “필드 하나 또는 몇 개만 바꾸는” 기능이 대부분이므로 `PATCH` 적합도가 높다.
  - 반면 실행 명령(command)이나 side effect 중심 엔드포인트는 여전히 `POST`가 맞다.

참고 출처:

- MDN PATCH
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/PATCH
- MDN PUT
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/PUT
- RFC 5789
  - https://www.rfc-editor.org/rfc/rfc5789

## 3. 현재 코드베이스 진단

### 3.1 기존 POST 엔드포인트

- [x] `POST /api/auth/signup`
- [x] `POST /api/auth/login`
- [x] `POST /api/auth/logout`
- [x] `POST /api/auth/change-password`
- [x] `POST /api/chat`
- [x] `POST /api/chat/resume`

### 3.2 현재 PATCH 엔드포인트

- [x] 없음

### 3.3 스키마/프론트 제약

- [x] `chat_sessions`에는 `title`, `pinned`, `archived` 컬럼이 없다.
- [x] 인증은 `auth_users` / `auth_sessions`로 분리되었고 `display_name`, `email`, `status` 필드는 이미 존재한다.
- [x] 프론트 workspace는 thread list / detail / auth guard를 이미 갖고 있다.
- [x] 좌측 thread list는 rename/pin UI를 넣기 좋은 구조지만 현재 편집 UI는 없다.

## 4. 기존 POST -> PATCH 변경 판단

### 4.1 유지해야 하는 POST

- [x] `POST /api/auth/signup`
  - 새 사용자 생성 액션이므로 `POST` 유지
- [x] `POST /api/auth/login`
  - 세션 발급 액션이므로 `POST` 유지
- [x] `POST /api/auth/logout`
  - 세션 종료 command 이므로 `POST` 유지
- [x] `POST /api/chat`
  - 새 실행 시작 command 이므로 `POST` 유지
- [x] `POST /api/chat/resume`
  - 그래프 재개 command 이므로 `POST` 유지

### 4.2 변경 여부를 검토할 수 있는 POST

- [x] `POST /api/auth/change-password`
  - 판단: 기본 권장안은 `POST` 유지
  - 이유: 현재 비밀번호 검증, password policy, 세션 revoke, 새 세션 발급까지 같이 일어나는 command 성격이 강하다.
  - 선택적 확장안:
    - `PATCH /api/users/me/password` alias 추가
    - 기존 `POST /api/auth/change-password`는 호환성 위해 일정 기간 유지

권장 결론:

- [x] 이번 계획에서는 기존 POST 엔드포인트를 즉시 PATCH로 “교체”하지 않는다.
- [x] 대신 PATCH가 자연스러운 신규 리소스 업데이트 엔드포인트 3개를 추가한다.
- [x] `change-password`는 v2에서 alias 도입 여부만 별도 검토한다.

## 5. 권장 PATCH 엔드포인트 3개

### 5.1 `PATCH /api/threads/{thread_id}`

목적:

- [ ] thread 제목 변경
- [ ] pinned on/off
- [ ] archived on/off

요청 예시:

```json
{
  "title": "프로젝트 회의 정리",
  "pinned": true,
  "archived": false
}
```

핵심 이유:

- thread 리소스 전체를 교체하지 않고 일부 메타데이터만 바꾸므로 `PATCH`가 적합하다.

### 5.2 `PATCH /api/users/me`

목적:

- [ ] `display_name` 수정
- [ ] `email` 수정

요청 예시:

```json
{
  "display_name": "Dr. Lee",
  "email": "drlee@example.com"
}
```

핵심 이유:

- 현재 로그인 사용자의 프로필 일부 필드만 수정하는 전형적인 partial update다.

### 5.3 `PATCH /api/users/{user_id}`

목적:

- [ ] 관리자에 의한 사용자 상태 변경
- [ ] 필요 시 role 변경은 후속 확장

요청 예시:

```json
{
  "status": "disabled"
}
```

핵심 이유:

- `status` 필드만 변경하는 관리자 부분 수정 시나리오다.
- 최종 라우트 형태는 `PATCH /api/users/{user_id}` 로 고정한다.
- `PATCH /api/users/{user_id}/status` 하위 라우트는 이번 계획에서 채택하지 않는다.
- 다만 UI는 admin 전용 영역이 필요하므로 backend 우선 도입 후 프론트는 최소 범위로 시작하는 것이 안전하다.

## 6. 데이터 모델 권장안

### 6.1 thread 메타데이터 저장 전략

현재 `chat_sessions` 직접 컬럼 추가는 위험하다.

권장 신규 테이블:

- [ ] `thread_profiles`
  - `id`
  - `thread_id` unique
  - `user_id`
  - `title_override`
  - `pinned`
  - `archived`
  - `created_at`
  - `updated_at`

추론:

- `chat_sessions`는 기존에 이미 생성되어 있을 가능성이 높아서 ALTER에 기대기 어렵다.
- `thread_profiles` 별도 테이블로 가면 현재 `create_all()` 체계에서도 비교적 안전하다.
- 목록 API에서는 `chat_sessions` + `chat_messages` 파생값에 `thread_profiles` override를 합성하면 된다.

### 6.2 사용자 프로필 저장 전략

- [x] `auth_users.display_name`
- [x] `auth_users.email`
- [x] `auth_users.status`

따라서 사용자 PATCH 2종은 신규 테이블 없이 구현 가능하다.

## 7. 백엔드 API 권장안

### 7.1 스키마

- [ ] `ThreadPatchRequest`
  - optional: `title`, `pinned`, `archived`
  - 최소 1개 필드 required
- [ ] `UserSelfPatchRequest`
  - optional: `display_name`, `email`
  - 최소 1개 필드 required
- [ ] `AdminUserPatchRequest`
  - optional: `status`
  - 필요 시 후속으로 `role`

### 7.2 라우터

- [ ] `PATCH /api/threads/{thread_id}`
- [ ] `PATCH /api/users/me`
- [ ] `PATCH /api/users/{user_id}`

### 7.3 응답 정책

- [ ] 200 with updated resource snapshot
- [ ] 잘못된 필드 조합 / empty body: 400
- [ ] validation 실패: 422
- [ ] ownership 불일치: 404
- [ ] 관리자 권한 없음: 403

## 8. 서비스 계층 권장안

### 8.1 `ThreadProfileService`

- [ ] `get_thread_profile(thread_id, user_id)`
- [ ] `upsert_thread_profile(thread_id, user_id, patch)`
- [ ] thread 소유권 검증
- [ ] title 길이/공백 normalize

### 8.2 `UserProfileService`

- [ ] `patch_self(user_id, patch)`
- [ ] email uniqueness 검사
- [ ] display_name normalization

### 8.3 `AdminUserService`

- [ ] `patch_user_status(target_user_id, patch)`
- [ ] 자기 자신 disable 금지 정책 검토
- [ ] admin role 검증

## 9. 프론트엔드 권장안

### 9.1 thread PATCH 연동

- [ ] thread list item overflow menu 또는 inline edit UI 추가
- [ ] title edit enter/save/cancel UX
- [ ] pinned 상태 시각적 표시
- [ ] archived thread 처리 정책
  - 기본 권장: 목록에서 숨기지 않고 후속 필터 기능 전까지 badge만 표시
- [ ] optimistic update + rollback

### 9.2 user self PATCH 연동

- [ ] account/settings panel 또는 modal 추가
- [ ] `display_name`, `email` 편집
- [ ] 저장 성공 시 auth context 갱신

### 9.3 admin user PATCH 연동

- [ ] v1은 backend 우선
- [ ] 프론트는 간단한 admin user management panel 또는 임시 admin page
- [ ] 일반 사용자에게는 숨김

## 10. 상세 작업 체크리스트

### Phase 0. 설계 고정

- [x] 기존 POST 엔드포인트 중 PATCH로 바꾸지 않을 대상을 확정한다.
- [x] `PATCH /api/threads/{thread_id}` 요청 범위(`title`, `pinned`, `archived`)를 확정한다.
- [x] thread 메타데이터용 별도 테이블(`thread_profiles`) 사용 여부를 확정한다.
- [x] `PATCH /api/users/me`, `PATCH /api/users/{user_id}` 권한 정책을 확정한다.
- [x] 관리자 상태 변경 라우트는 `PATCH /api/users/{user_id}` 로 고정하고 `/status` 하위 라우트는 사용하지 않기로 확정한다.

### Phase 1. 모델/스키마

- [x] `apps/backend/models/thread_profile.py` 추가
- [x] `apps/backend/models/__init__.py` 등록
- [x] `apps/backend/schemas/thread_patch.py` 또는 기존 thread schema 확장
- [x] `apps/backend/schemas/user_patch.py` 추가

### Phase 2. 서비스 계층

- [x] `apps/backend/services/thread_profile_service.py`
- [x] 기존 `thread_service.py` 와 thread summary/detail 합성 로직 연결
- [x] `apps/backend/services/user_profile_service.py`
- [x] `apps/backend/services/admin_user_service.py`

### Phase 3. 백엔드 라우터

- [x] `PATCH /api/threads/{thread_id}` 구현
- [x] `PATCH /api/users/me` 구현
- [x] `PATCH /api/users/{user_id}` 구현
- [x] 필요 시 `POST /api/auth/change-password` 유지 사유를 API 문서에 명시

### Phase 4. 프론트 thread 연동

- [x] thread rename UI
- [x] thread pin toggle UI
- [x] archived badge or state 반영
- [x] optimistic patch / rollback

### Phase 5. 프론트 user 연동

- [x] profile edit UI
- [x] auth context refresh
- [x] admin 전용 user status UI 또는 최소 페이지

### Phase 6. 테스트

- [x] backend tests
  - [x] thread rename success
  - [x] thread pinned toggle success
  - [x] thread ownership 404
  - [x] user self patch success
  - [x] duplicate email conflict
  - [x] admin-only status patch
  - [x] non-admin forbidden
- [x] frontend tests
  - [x] thread rename optimistic update
  - [x] thread pin toggle
  - [x] profile edit save
  - [x] admin status update UI gating

### Phase 7. 수동 검증

- [ ] thread 제목 변경 후 목록/헤더/새로고침 반영 확인
- [ ] pinned 토글 후 목록 상태 유지 확인
- [ ] 다른 사용자가 내 thread PATCH 시 404 확인
- [ ] profile 수정 후 헤더 표시 이름 갱신 확인
- [ ] admin이 사용자 disable 후 해당 사용자의 로그인/접근 제한 확인

## 11. 리스크 및 주의사항

- [ ] `chat_sessions` 직접 컬럼 추가 전제는 현재 운영 방식에서 위험하다.
- [ ] thread rename/pin을 위해 thread summary query가 더 복잡해질 수 있다.
- [ ] admin user patch UI는 일반 사용자에게 노출되면 안 된다.
- [ ] archived semantics를 너무 빨리 넣으면 thread list UX가 불안정해질 수 있다.
- [ ] `change-password`를 PATCH로 성급히 바꾸면 command 성격과 충돌할 수 있다.

## 12. 완료 기준

- [ ] 기존 POST 엔드포인트 중 유지/비유지 정책이 문서화된다.
- [ ] `PATCH /api/threads/{thread_id}` 가 title/pinned/archive를 부분 수정할 수 있다.
- [ ] `PATCH /api/users/me` 가 display_name/email 부분 수정을 지원한다.
- [ ] `PATCH /api/users/{user_id}` 가 admin 전용 status 수정을 지원한다.
- [ ] 프론트에서 thread rename / pin / profile edit 가 자연스럽게 연결된다.
- [ ] ownership / auth / admin 권한 검증이 회귀 없이 유지된다.

## 13. 구현 순서 권장

1. POST 유지/변경 정책 먼저 확정
2. thread 메타데이터 저장 모델 추가
3. `PATCH /api/threads/{thread_id}` + 프론트 rename/pin 먼저 구현
4. `PATCH /api/users/me` 구현
5. `PATCH /api/users/{user_id}` admin 기능 추가
6. 문서/테스트/수동 검증 마무리
