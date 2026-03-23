import os
import pytest
from datetime import datetime, timedelta

# Set mock environment variables BEFORE any application code is imported.
# This prevents Pydantic validation errors when module-level tools
# (like TavilySearch or OpenAI chat models) are instantiated during pytest collection.
os.environ["OPENAI_API_KEY"] = "mock-openai-key-for-testing"
os.environ["TAVILY_API_KEY"] = "mock-tavily-key-for-testing"
os.environ["USER_AGENT"] = "test-agent"


@pytest.fixture(autouse=True)
def stub_chat_async_session_local(monkeypatch):
    class DummyResult:
        def scalar_one_or_none(self):
            return None

        def scalars(self):
            return self

        def all(self):
            return []

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, *args, **kwargs):
            return DummyResult()

        def add(self, *args, **kwargs):
            pass

        def add_all(self, *args, **kwargs):
            pass

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def refresh(self, *args, **kwargs):
            pass

        async def rollback(self):
            pass

        async def close(self):
            pass

    class DummySessionFactory:
        def __call__(self):
            return DummySession()

    monkeypatch.setattr("api.routes.chat.AsyncSessionLocal", DummySessionFactory())
    monkeypatch.setattr("core.database.AsyncSessionLocal", DummySessionFactory())


@pytest.fixture(autouse=True)
def stub_auth_dependencies(monkeypatch, request):
    if request.node.get_closest_marker("no_auth_override"):
        yield
        return

    from main import app
    from models.auth import AuthSession, AuthUser, KST
    from services.auth_service import hash_password
    from services.security_service import (
        get_current_session,
        get_current_user,
        require_csrf,
    )

    user = AuthUser(
        id="test-user",
        login_id="tester",
        password_hash=hash_password("abcdefghijklmn1"),
        role="user",
        status="active",
        must_change_password=False,
    )
    session = AuthSession(
        id="test-session",
        user_id="test-user",
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        expires_at=datetime.now(KST) + timedelta(hours=1),
    )
    session.user = user

    async def override_current_user():
        return user

    async def override_current_session():
        return session

    async def override_require_csrf():
        return None

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_current_session] = override_current_session
    app.dependency_overrides[require_csrf] = override_require_csrf
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.fixture(autouse=True)
def stub_thread_ownership_guard(monkeypatch, request):
    if request.node.get_closest_marker("real_thread_ownership"):
        yield
        return

    async def allow_thread_access(*args, **kwargs):
        return None

    monkeypatch.setattr("api.routes.chat._ensure_thread_owned_by_user", allow_thread_access)
    yield
