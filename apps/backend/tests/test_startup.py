import socket

import pytest

from main import initialize_runtime_dependencies


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
