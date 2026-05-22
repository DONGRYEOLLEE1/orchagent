import pytest
from fastapi.testclient import TestClient

from core.database import get_db
from main import app

client = TestClient(app)


async def _override_get_db():
    yield object()


@pytest.mark.no_auth_override
@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("GET", "/api/threads", None),
        ("POST", "/api/chat", {"message": "hello", "thread_id": "thread-1"}),
    ],
    ids=["threads_list", "chat_post"],
)
def test_protected_route_requires_auth(method, path, json_body):
    """Any caller missing auth cookies must receive 401 from protected routes."""
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.request(method, path, json=json_body)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
