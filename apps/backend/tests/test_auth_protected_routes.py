import pytest
from fastapi.testclient import TestClient

from core.database import get_db
from main import app

client = TestClient(app)


async def _override_get_db():
    yield object()


@pytest.mark.no_auth_override
def test_threads_requires_auth():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.get("/api/threads")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.no_auth_override
def test_chat_requires_auth():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.post("/api/chat", json={"message": "hello", "thread_id": "thread-1"})
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
