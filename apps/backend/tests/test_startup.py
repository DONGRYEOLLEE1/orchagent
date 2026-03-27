import socket
from unittest.mock import AsyncMock

import pytest

from main import initialize_runtime_dependencies, _initialize_runtime_dependencies_once


@pytest.mark.asyncio
async def test_initialize_runtime_dependencies_retries_until_success(monkeypatch):
    attempts = 0
    sleep_calls: list[float] = []

    async def flaky_initializer():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise socket.gaierror(-3, "Temporary failure in name resolution")

    async def fake_sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr("main._initialize_runtime_dependencies_once", flaky_initializer)
    monkeypatch.setattr("main.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("main.settings.STARTUP_MAX_RETRIES", 3)
    monkeypatch.setattr("main.settings.STARTUP_RETRY_DELAY_SECONDS", 0.01)

    await initialize_runtime_dependencies()

    assert attempts == 3
    assert sleep_calls == [0.01, 0.01]


@pytest.mark.asyncio
async def test_initialize_runtime_dependencies_raises_after_retry_budget(monkeypatch):
    attempts = 0

    async def failing_initializer():
        nonlocal attempts
        attempts += 1
        raise socket.gaierror(-3, "Temporary failure in name resolution")

    async def fake_sleep(delay: float):
        return None

    monkeypatch.setattr(
        "main._initialize_runtime_dependencies_once", failing_initializer
    )
    monkeypatch.setattr("main.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("main.settings.STARTUP_MAX_RETRIES", 2)
    monkeypatch.setattr("main.settings.STARTUP_RETRY_DELAY_SECONDS", 0.01)

    with pytest.raises(socket.gaierror):
        await initialize_runtime_dependencies()

    assert attempts == 2


@pytest.mark.asyncio
async def test_initialize_runtime_dependencies_once_bootstraps_admin(monkeypatch):
    sync_calls: list[str] = []

    class DummyConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def run_sync(self, fn):
            sync_calls.append(fn.__name__)

    class DummyEngine:
        def begin(self):
            return DummyConn()

    class DummyCheckpointer:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def setup(self):
            sync_calls.append("checkpointer.setup")

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class DummySessionFactory:
        def __call__(self):
            return DummySession()

    bootstrap_calls = []
    pricing_calls = []
    timezone_calls = []
    schema_patch_calls = []

    async def fake_bootstrap_admin(db):
        bootstrap_calls.append(db)

    async def fake_ensure_pricing(db):
        pricing_calls.append(db)

    async def fake_ensure_timezone(db):
        timezone_calls.append(db)

    async def fake_ensure_schema_patch(db):
        schema_patch_calls.append(db)

    async def fake_ensure_chat_message_patch(db):
        schema_patch_calls.append(db)

    monkeypatch.setattr("main.engine", DummyEngine())
    monkeypatch.setattr(
        "main.AsyncPostgresSaver",
        type(
            "DummySaver",
            (),
            {"from_conn_string": staticmethod(lambda conn: DummyCheckpointer())},
        ),
    )
    monkeypatch.setattr("main.AsyncSessionLocal", DummySessionFactory())
    monkeypatch.setattr("main.DatabaseTimeService.ensure_kst_timezone", fake_ensure_timezone)
    monkeypatch.setattr("main.SchemaPatchService.ensure_trace_event_columns", fake_ensure_schema_patch)
    monkeypatch.setattr("main.SchemaPatchService.ensure_chat_message_attachment_columns", fake_ensure_chat_message_patch)
    monkeypatch.setattr("main.ensure_bootstrap_admin", fake_bootstrap_admin)
    monkeypatch.setattr("main.LLMPricingService.ensure_default_pricing_snapshots", fake_ensure_pricing)
    monkeypatch.setattr("main.initialize_memory_store", AsyncMock())
    monkeypatch.setattr("main.MemoryStoreService.backfill_active_memories", AsyncMock())

    await _initialize_runtime_dependencies_once()

    assert "create_all" in sync_calls
    assert "checkpointer.setup" in sync_calls
    assert len(timezone_calls) == 1
    assert len(schema_patch_calls) == 2
    assert len(bootstrap_calls) == 1
    assert len(pricing_calls) == 1
