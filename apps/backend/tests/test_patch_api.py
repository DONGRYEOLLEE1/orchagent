from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from core.database import get_db
from main import app
from models.auth import AuthUser
from services.security_service import get_current_admin_user
from services.thread_service import ThreadSummary

client = TestClient(app)


async def _override_get_db():
    yield object()


def test_patch_thread_updates_title_and_pinned(monkeypatch):
    summary = ThreadSummary(
        thread_id="thread-1",
        title="Renamed thread",
        preview="Latest reply",
        created_at=datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc),
        last_activity_at=datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc),
        message_count=2,
        latest_status="completed",
        checkpoint_id="cp-1",
        pinned=True,
        archived=False,
    )

    async def mock_get_chat_session(db, thread_id, *, user_id=None):
        assert thread_id == "thread-1"
        assert user_id == "test-user"
        return object()

    async def mock_upsert(*args, **kwargs):
        return None

    async def mock_get_thread_summary(db, thread_id, *, user_id):
        assert thread_id == "thread-1"
        assert user_id == "test-user"
        return summary

    from services.thread_profile_service import ThreadProfileService
    from services.thread_service import ThreadService

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(ThreadService, "get_chat_session", mock_get_chat_session)
    monkeypatch.setattr(ThreadProfileService, "upsert_thread_profile", mock_upsert)
    monkeypatch.setattr(ThreadService, "get_thread_summary", mock_get_thread_summary)
    try:
        response = client.patch(
            "/api/threads/thread-1",
            json={"title": "Renamed thread", "pinned": True},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed thread"
    assert response.json()["pinned"] is True


def test_patch_user_self_returns_409_for_duplicate_email(monkeypatch):
    from services.auth_service import DuplicateEmailError
    from services.user_profile_service import UserProfileService

    async def mock_patch_self(*args, **kwargs):
        raise DuplicateEmailError("Email is already in use.")

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(UserProfileService, "patch_self", mock_patch_self)
    try:
        response = client.patch(
            "/api/users/me",
            json={"email": "dup@example.com"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 409


def test_patch_user_status_requires_admin(monkeypatch):
    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.patch(
            "/api/users/user-2",
            json={"status": "disabled"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin privileges required"


def test_patch_user_status_updates_target_for_admin(monkeypatch):
    admin = AuthUser(
        id="admin-1",
        login_id="admin",
        password_hash="hashed",
        role="admin",
        status="active",
        must_change_password=False,
    )
    updated_user = AuthUser(
        id="user-2",
        login_id="user2",
        password_hash="hashed",
        role="user",
        status="disabled",
        must_change_password=False,
    )

    async def override_admin_user():
        return admin

    from services.admin_user_service import AdminUserService

    async def mock_patch_user_status(*args, **kwargs):
        assert kwargs["actor_user_id"] == "admin-1"
        assert kwargs["target_user_id"] == "user-2"
        assert kwargs["status"] == "disabled"
        return updated_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin_user] = override_admin_user
    monkeypatch.setattr(AdminUserService, "patch_user_status", mock_patch_user_status)
    try:
        response = client.patch(
            "/api/users/user-2",
            json={"status": "disabled"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_admin_user, None)

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
