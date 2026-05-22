from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from main import app
from models.auth import AuthSession, AuthUser, KST
from services.auth_service import IssuedSession, hash_password
from services.security_service import get_current_session, get_current_user, require_csrf

client = TestClient(app)


def _build_user() -> AuthUser:
    return AuthUser(
        id="user-1",
        login_id="user1",
        password_hash=hash_password("abcdefghijklmn1"),
        role="user",
        status="active",
        must_change_password=False,
    )


def _build_issued_session(token: str = "session-token") -> IssuedSession:
    return IssuedSession(
        session=AuthSession(
            id="session-1",
            user_id="user-1",
            session_token_hash="session-hash",
            csrf_token_hash="csrf-hash",
            expires_at=datetime.now(KST) + timedelta(hours=1),
        ),
        session_token=token,
        csrf_token="csrf-token",
    )


def test_login_sets_auth_cookies(monkeypatch):
    """Successful login must attach the orch_session cookie + return 200."""
    user = _build_user()
    issued_session = _build_issued_session()

    async def mock_authenticate_user(*args, **kwargs):
        return user

    async def mock_issue_session(*args, **kwargs):
        return issued_session

    monkeypatch.setattr("api.routes.auth.authenticate_user", mock_authenticate_user)
    monkeypatch.setattr("api.routes.auth.issue_session", mock_issue_session)

    response = client.post(
        "/api/auth/login",
        json={"login_id": "user1", "password": "abcdefghijklmn1"},
        headers={"origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert "orch_session=session-token" in response.headers.get("set-cookie", "")


def test_login_returns_401_for_invalid_credentials(monkeypatch):
    async def mock_authenticate_user(*args, **kwargs):
        from services.auth_service import InvalidCredentialsError

        raise InvalidCredentialsError("Invalid credentials.")

    monkeypatch.setattr("api.routes.auth.authenticate_user", mock_authenticate_user)

    response = client.post(
        "/api/auth/login",
        json={"login_id": "user1", "password": "wrong-password"},
        headers={"origin": "http://localhost:3000"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_me_returns_current_user_with_must_change_password_flag():
    user = AuthUser(
        id="user-1",
        login_id="admin",
        password_hash=hash_password("admin1"),
        role="admin",
        status="active",
        must_change_password=True,
    )

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = client.get("/api/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True


def test_logout_revokes_session_and_clears_cookies(monkeypatch):
    user = _build_user()
    session = AuthSession(
        id="session-1",
        user_id="user-1",
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        expires_at=datetime.now(KST) + timedelta(hours=1),
    )
    session.user = user

    async def override_current_session():
        return session

    async def override_require_csrf():
        return None

    async def mock_revoke_session(*args, **kwargs):
        return None

    monkeypatch.setattr("api.routes.auth.revoke_session", mock_revoke_session)
    app.dependency_overrides[get_current_session] = override_current_session
    app.dependency_overrides[require_csrf] = override_require_csrf
    try:
        response = client.post("/api/auth/logout")
    finally:
        app.dependency_overrides.pop(get_current_session, None)
        app.dependency_overrides.pop(require_csrf, None)

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out"
    assert "Max-Age=0" in response.headers.get("set-cookie", "")


def test_change_password_issues_new_session_and_clears_flag(monkeypatch):
    """change-password rotates the session AND clears must_change_password."""
    user = AuthUser(
        id="user-1",
        login_id="admin",
        password_hash=hash_password("admin1"),
        role="admin",
        status="active",
        must_change_password=True,
    )
    session = AuthSession(
        id="session-1",
        user_id="user-1",
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        expires_at=datetime.now(KST) + timedelta(hours=1),
    )
    session.user = user
    issued_session = _build_issued_session(token="new-session-token")

    async def override_current_session():
        return session

    async def override_require_csrf():
        return None

    async def mock_change_password(*args, **kwargs):
        user.must_change_password = False
        user.password_hash = hash_password("abcdefghijklmn2")
        return user

    async def mock_revoke_user_sessions(*args, **kwargs):
        return 1

    async def mock_issue_session(*args, **kwargs):
        return issued_session

    monkeypatch.setattr("api.routes.auth.change_password", mock_change_password)
    monkeypatch.setattr("api.routes.auth.revoke_user_sessions", mock_revoke_user_sessions)
    monkeypatch.setattr("api.routes.auth.issue_session", mock_issue_session)
    app.dependency_overrides[get_current_session] = override_current_session
    app.dependency_overrides[require_csrf] = override_require_csrf
    try:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin1",
                "new_password": "abcdefghijklmn2",
            },
            headers={"origin": "http://localhost:3000"},
        )
    finally:
        app.dependency_overrides.pop(get_current_session, None)
        app.dependency_overrides.pop(require_csrf, None)

    assert response.status_code == 200
    assert response.json()["must_change_password"] is False
    assert "orch_session=new-session-token" in response.headers.get("set-cookie", "")


def test_change_password_returns_400_for_policy_error(monkeypatch):
    user = AuthUser(
        id="user-1",
        login_id="admin",
        password_hash=hash_password("adminpassword5x"),
        role="admin",
        status="active",
        must_change_password=False,
    )
    session = AuthSession(
        id="session-1",
        user_id="user-1",
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        expires_at=datetime.now(KST) + timedelta(hours=1),
    )
    session.user = user

    async def override_current_session():
        return session

    async def override_require_csrf():
        return None

    async def mock_change_password(*args, **kwargs):
        from services.auth_service import PasswordPolicyError

        raise PasswordPolicyError("Password must include at least one number.")

    monkeypatch.setattr("api.routes.auth.change_password", mock_change_password)
    app.dependency_overrides[get_current_session] = override_current_session
    app.dependency_overrides[require_csrf] = override_require_csrf
    try:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "adminpassword5x",
                "new_password": "weakpassword",
            },
            headers={"origin": "http://localhost:3000"},
        )
    finally:
        app.dependency_overrides.pop(get_current_session, None)
        app.dependency_overrides.pop(require_csrf, None)

    assert response.status_code == 400
    assert "Password must include at least one number" in response.json()["detail"]
