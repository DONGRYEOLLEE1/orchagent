from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from models.auth import AuthSession, AuthUser, KST
from core.config import Settings
from services.auth_service import (
    DuplicateLoginIdError,
    IssuedSession,
    authenticate_user,
    change_password,
    create_user,
    ensure_bootstrap_admin,
    get_auth_session_by_token,
    hash_password,
    issue_session,
    revoke_session,
    validate_password_policy,
    verify_password,
    verify_csrf_token,
)


def test_hash_password_round_trip_verification():
    password = "admin1"

    stored_hash = hash_password(password)

    assert stored_hash.startswith("pbkdf2_sha256$")
    assert verify_password(password, stored_hash)
    assert not verify_password("wrong-password", stored_hash)


def test_validate_password_policy_requires_lowercase_and_number():
    with pytest.raises(Exception):
        validate_password_policy("AAAA")

    with pytest.raises(Exception):
        validate_password_policy("abcd")

    validate_password_policy("abc1")


def test_auth_allowed_origins_parses_csv():
    settings = Settings(
        AUTH_ALLOWED_ORIGINS="http://localhost:3000, http://127.0.0.1:3000"
    )

    assert settings.auth_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


@pytest.mark.asyncio
async def test_ensure_bootstrap_admin_creates_default_admin(monkeypatch):
    result = SimpleNamespace(scalar_one_or_none=lambda: None)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_ENABLED", True)
    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_LOGIN_ID", "admin")
    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_PASSWORD", "admin1")

    admin_user = await ensure_bootstrap_admin(db)

    assert admin_user is not None
    assert admin_user.login_id == "admin"
    assert admin_user.role == "admin"
    assert admin_user.status == "active"
    assert admin_user.must_change_password is True
    assert verify_password("admin1", admin_user.password_hash)
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(admin_user)


@pytest.mark.asyncio
async def test_ensure_bootstrap_admin_is_idempotent(monkeypatch):
    existing_user = SimpleNamespace(login_id="admin", role="admin")
    result = SimpleNamespace(scalar_one_or_none=lambda: existing_user)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_ENABLED", True)
    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_LOGIN_ID", "admin")
    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_PASSWORD", "admin1")

    returned_user = await ensure_bootstrap_admin(db)

    assert returned_user is existing_user
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_user_raises_for_duplicate_login_id(monkeypatch):
    existing_user = AuthUser(
        login_id="existing",
        password_hash=hash_password("abcdefghijklmn1"),
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: existing_user)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = Mock()

    with pytest.raises(DuplicateLoginIdError):
        await create_user(
            db,
            login_id=" existing ",
            password="abcdefghijklmn1",
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_authenticate_user_rejects_invalid_password():
    existing_user = AuthUser(
        login_id="existing",
        password_hash=hash_password("abcdefghijklmn1"),
        status="active",
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: existing_user)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(Exception):
        await authenticate_user(db, login_id="existing", password="wrongpass123456")


@pytest.mark.asyncio
async def test_issue_session_stores_hashed_tokens_and_can_be_resolved():
    user = AuthUser(
        id="user-1",
        login_id="user1",
        password_hash=hash_password("abcdefghijklmn1"),
        status="active",
    )
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    issued = await issue_session(db, user=user, user_agent="ua", ip_address="127.0.0.1")

    assert isinstance(issued, IssuedSession)
    assert issued.session.user_id == "user-1"
    assert issued.session.session_token_hash != issued.session_token
    assert verify_csrf_token(issued.csrf_token, issued.session)


@pytest.mark.asyncio
async def test_get_auth_session_by_token_filters_revoked_and_expired_sessions():
    session = AuthSession(
        user_id="user-1",
        session_token_hash="hash",
        csrf_token_hash="csrf",
        expires_at=datetime.now(KST) + timedelta(hours=1),
        revoked_at=None,
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: session)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "services.auth_service._token_hash",
        lambda raw_token: "hash",
    )
    try:
        resolved = await get_auth_session_by_token(db, "raw-token")
    finally:
        monkeypatch.undo()

    assert resolved is session


@pytest.mark.asyncio
async def test_revoke_session_sets_revoked_at():
    session = AuthSession(
        id="session-1",
        user_id="user-1",
        session_token_hash="hash",
        csrf_token_hash="csrf",
        expires_at=datetime.now(KST) + timedelta(hours=1),
        revoked_at=None,
    )
    db = AsyncMock()
    db.commit = AsyncMock()

    await revoke_session(db, session)

    assert session.revoked_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_password_clears_must_change_password():
    user = AuthUser(
        login_id="user1",
        password_hash=hash_password("abcdefghijklmn1"),
        must_change_password=True,
    )
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    updated = await change_password(
        db,
        user=user,
        new_password="abcdefghijklmn2",
    )

    assert updated.must_change_password is False
    assert verify_password("abcdefghijklmn2", updated.password_hash)
