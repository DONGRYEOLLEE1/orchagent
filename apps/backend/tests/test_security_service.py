from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from models.auth import AuthSession, AuthUser, KST
from services.auth_service import hash_password
from services.security_service import (
    apply_auth_cookies,
    clear_auth_cookies,
    get_current_session,
    get_current_user,
    request_client_ip,
    request_user_agent,
    require_csrf,
)


def build_request(
    *,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    client: tuple[str, int] = ("127.0.0.1", 8000),
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/api/test",
        "raw_path": b"/api/test",
        "query_string": b"",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {}).items()
        ],
        "client": client,
        "server": ("testserver", 80),
    }
    return Request(scope)


def _build_session() -> AuthSession:
    return AuthSession(
        user_id="user-1",
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        expires_at=datetime.now(KST) + timedelta(hours=1),
    )


def test_apply_and_clear_auth_cookies():
    """apply_auth_cookies writes orch_session/orch_csrf; clear sets Max-Age=0."""
    response = Response()
    session = _build_session()
    from services.auth_service import IssuedSession

    apply_auth_cookies(
        response,
        IssuedSession(session=session, session_token="session-token", csrf_token="csrf-token"),
    )
    raw = b"\n".join(value for key, value in response.raw_headers if key == b"set-cookie")
    assert b"orch_session=session-token" in raw
    assert b"orch_csrf=csrf-token" in raw

    clear_auth_cookies(response)
    raw = b"\n".join(value for key, value in response.raw_headers if key == b"set-cookie")
    assert b"Max-Age=0" in raw


@pytest.mark.asyncio
async def test_get_current_session_raises_when_missing():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_session(None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_csrf_accepts_match_and_rejects_missing_header():
    """Matching cookie + header passes; missing header must produce 403."""
    user = AuthUser(
        id="user-1",
        login_id="user1",
        password_hash=hash_password("abcdefghijklmn1"),
    )
    session = _build_session()
    session.user = user

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "services.security_service.verify_csrf_token",
        lambda token, current: token == "csrf-token",
    )
    try:
        request = build_request(
            headers={
                "origin": "http://localhost:3000",
                "referer": "http://localhost:3000/login",
            }
        )
        # Matching cookie + header should pass without raising.
        await require_csrf(
            request,
            session=session,
            csrf_cookie="csrf-token",
            csrf_header="csrf-token",
        )
        # Missing header must produce 403.
        with pytest.raises(HTTPException) as exc_info:
            await require_csrf(
                request, session=session, csrf_cookie="csrf-token", csrf_header=None
            )
        assert exc_info.value.status_code == 403
    finally:
        monkeypatch.undo()


def test_request_context_helpers_use_forwarded_headers():
    request = build_request(
        method="GET",
        headers={
            "user-agent": "pytest-agent",
            "x-forwarded-for": "203.0.113.10, 127.0.0.1",
        },
    )

    assert request_user_agent(request) == "pytest-agent"
    assert request_client_ip(request) == "203.0.113.10"
