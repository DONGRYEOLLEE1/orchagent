from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from core.database import get_db
from main import app

client = TestClient(app)


async def _override_get_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    yield db


def test_get_memory_settings_returns_settings_payload(monkeypatch):
    from services.memory_service import MemoryService

    created_at = datetime(2026, 3, 26, 2, 0, 0, tzinfo=timezone.utc)

    async def mock_get_or_create_settings(db, user_id):
        assert user_id == "test-user"
        return SimpleNamespace(
            user_id=user_id,
            memory_enabled=True,
            allow_explicit_memory=True,
            allow_inferred_memory=True,
            allow_chat_history_reference=True,
            default_memory_mode="enabled",
            created_at=created_at,
            updated_at=created_at,
        )

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(MemoryService, "get_or_create_settings", mock_get_or_create_settings)
    try:
        response = client.get("/api/users/me/memory/settings")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["memory_enabled"] is True
    assert response.json()["default_memory_mode"] == "enabled"


def test_list_personal_memories_returns_entries(monkeypatch):
    from services.memory_service import MemoryService

    created_at = datetime(2026, 3, 26, 2, 0, 0, tzinfo=timezone.utc)
    memory_id = uuid4()

    async def mock_list_memories(db, *, user_id, limit):
        assert user_id == "test-user"
        assert limit == 100
        return [
            SimpleNamespace(
                id=memory_id,
                user_id=user_id,
                thread_id=None,
                scope_type="user_global",
                source_type="inferred",
                status="active",
                category="personal_interest",
                title="좋아하는 아티스트",
                content_text="가수 백예린을 좋아한다",
                confidence=91,
                salience=88,
                created_at=created_at,
                updated_at=created_at,
                deleted_at=None,
            )
        ]

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(MemoryService, "list_memories", mock_list_memories)
    try:
        response = client.get("/api/users/me/memory")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["memories"][0]["title"] == "좋아하는 아티스트"


def test_delete_personal_memory_returns_404_when_missing(monkeypatch):
    from services.memory_service import MemoryService

    async def mock_delete_memory(db, *, user_id, memory_id):
        assert user_id == "test-user"
        return None

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(MemoryService, "delete_memory", mock_delete_memory)
    try:
        response = client.delete(f"/api/users/me/memory/{uuid4()}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Memory not found"
