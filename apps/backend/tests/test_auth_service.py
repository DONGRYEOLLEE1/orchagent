from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from models.auth import AuthSession, AuthUser, KST
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
    verify_password,
    verify_csrf_token,
)


def test_hash_password_round_trip_verification():
    """pbkdf2 hashes must verify the original password but reject a wrong one."""
    stored_hash = hash_password("admin1")

    assert stored_hash.startswith("pbkdf2_sha256$")
    assert verify_password("admin1", stored_hash)
    assert not verify_password("wrong-password", stored_hash)


@pytest.mark.asyncio
async def test_ensure_bootstrap_admin_is_idempotent_and_creates_on_first_run(monkeypatch):
    """First run creates the admin row; subsequent runs return the existing user."""
    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_ENABLED", True)
    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_LOGIN_ID", "admin")
    monkeypatch.setattr("services.auth_service.settings.AUTH_BOOTSTRAP_ADMIN_PASSWORD", "admin1")

    # First run: no existing user → admin is created.
    create_result = SimpleNamespace(scalar_one_or_none=lambda: None)
    db_create = AsyncMock()
    db_create.execute = AsyncMock(return_value=create_result)
    db_create.add = Mock()
    db_create.commit = AsyncMock()
    db_create.refresh = AsyncMock()

    admin_user = await ensure_bootstrap_admin(db_create)
    assert admin_user.login_id == "admin"
    assert admin_user.role == "admin"
    assert admin_user.must_change_password is True
    assert verify_password("admin1", admin_user.password_hash)
    db_create.add.assert_called_once()

    # Second run: existing user → no insertion.
    existing_user = SimpleNamespace(login_id="admin", role="admin")
    idempotent_result = SimpleNamespace(scalar_one_or_none=lambda: existing_user)
    db_idem = AsyncMock()
    db_idem.execute = AsyncMock(return_value=idempotent_result)
    db_idem.add = Mock()
    db_idem.commit = AsyncMock()
    db_idem.refresh = AsyncMock()

    assert await ensure_bootstrap_admin(db_idem) is existing_user
    db_idem.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_user_raises_for_duplicate_login_id():
    """Duplicate login_id (with whitespace) must be rejected and not committed."""
    existing_user = AuthUser(
        login_id="existing",
        password_hash=hash_password("abcdefghijklmn1"),
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: existing_user)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = Mock()

    with pytest.raises(DuplicateLoginIdError):
        await create_user(db, login_id=" existing ", password="abcdefghijklmn1")

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
    # Raw tokens must not match the persisted hash.
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
    monkeypatch.setattr("services.auth_service._token_hash", lambda raw_token: "hash")
    try:
        resolved = await get_auth_session_by_token(db, "raw-token")
    finally:
        monkeypatch.undo()

    assert resolved is session


@pytest.mark.asyncio
async def test_revoke_session_and_change_password_persist_state():
    """revoke_session sets revoked_at; change_password clears must_change_password."""
    session = AuthSession(
        id="session-1",
        user_id="user-1",
        session_token_hash="hash",
        csrf_token_hash="csrf",
        expires_at=datetime.now(KST) + timedelta(hours=1),
        revoked_at=None,
    )
    db_revoke = AsyncMock()
    db_revoke.commit = AsyncMock()
    await revoke_session(db_revoke, session)
    assert session.revoked_at is not None

    user = AuthUser(
        login_id="user1",
        password_hash=hash_password("abcdefghijklmn1"),
        must_change_password=True,
    )
    db_change = AsyncMock()
    db_change.commit = AsyncMock()
    db_change.refresh = AsyncMock()

    updated = await change_password(db_change, user=user, new_password="abcdefghijklmn2")

    assert updated.must_change_password is False
    assert verify_password("abcdefghijklmn2", updated.password_hash)
