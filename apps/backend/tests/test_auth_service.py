from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.config import Settings
from services.auth_service import ensure_bootstrap_admin, hash_password, verify_password


def test_hash_password_round_trip_verification():
    password = "admin1"

    stored_hash = hash_password(password)

    assert stored_hash.startswith("pbkdf2_sha256$")
    assert verify_password(password, stored_hash)
    assert not verify_password("wrong-password", stored_hash)


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
