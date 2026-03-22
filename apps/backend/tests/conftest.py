import os
import pytest

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
