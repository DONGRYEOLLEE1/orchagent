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
            instructions_enabled=True,
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
    assert response.json()["instructions_enabled"] is True
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


def test_get_personalization_settings_returns_shared_settings_payload(monkeypatch):
    from services.memory_service import MemoryService

    created_at = datetime(2026, 3, 26, 2, 0, 0, tzinfo=timezone.utc)

    async def mock_get_or_create_settings(db, user_id):
        assert user_id == "test-user"
        return SimpleNamespace(
            user_id=user_id,
            memory_enabled=True,
            instructions_enabled=False,
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
        response = client.get("/api/users/me/personalization/settings")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["instructions_enabled"] is False


def test_patch_personalization_settings_updates_instruction_toggle(monkeypatch):
    from services.memory_service import MemoryService

    created_at = datetime(2026, 3, 26, 2, 0, 0, tzinfo=timezone.utc)

    async def mock_update_settings(
        db,
        *,
        user_id,
        instructions_enabled=None,
        **_kwargs,
    ):
        assert user_id == "test-user"
        assert instructions_enabled is False
        return SimpleNamespace(
            user_id=user_id,
            memory_enabled=True,
            instructions_enabled=False,
            allow_explicit_memory=True,
            allow_inferred_memory=True,
            allow_chat_history_reference=True,
            default_memory_mode="enabled",
            created_at=created_at,
            updated_at=created_at,
        )

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(MemoryService, "update_settings", mock_update_settings)
    try:
        response = client.patch(
            "/api/users/me/personalization/settings",
            json={"instructions_enabled": False},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["instructions_enabled"] is False


def test_list_personalization_instructions_returns_entries(monkeypatch):
    from services.personalization_instruction_service import (
        PersonalizationInstructionService,
    )

    created_at = datetime(2026, 3, 26, 2, 0, 0, tzinfo=timezone.utc)
    instruction_id = uuid4()

    async def mock_list_instructions(db, *, user_id, enabled_only=False):
        assert user_id == "test-user"
        assert enabled_only is False
        return [
            SimpleNamespace(
                id=instruction_id,
                user_id=user_id,
                instruction_type="response_style",
                title="설명 방식",
                content_text="추상 개념은 예시와 함께 설명한다",
                enabled=True,
                created_at=created_at,
                updated_at=created_at,
            )
        ]

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        PersonalizationInstructionService,
        "list_instructions",
        mock_list_instructions,
    )
    try:
        response = client.get("/api/users/me/personalization/instructions")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["instructions"][0]["title"] == "설명 방식"


def test_create_personalization_instruction_returns_created_entry(monkeypatch):
    from services.personalization_instruction_service import (
        PersonalizationInstructionService,
    )

    created_at = datetime(2026, 3, 26, 2, 0, 0, tzinfo=timezone.utc)
    instruction_id = uuid4()

    async def mock_create_instruction(
        db,
        *,
        user_id,
        instruction_type,
        title,
        content_text,
        enabled,
    ):
        assert user_id == "test-user"
        assert instruction_type == "response_style"
        assert enabled is True
        return SimpleNamespace(
            id=instruction_id,
            user_id=user_id,
            instruction_type=instruction_type,
            title=title,
            content_text=content_text,
            enabled=enabled,
            created_at=created_at,
            updated_at=created_at,
        )

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        PersonalizationInstructionService,
        "create_instruction",
        mock_create_instruction,
    )
    try:
        response = client.post(
            "/api/users/me/personalization/instructions",
            json={
                "instruction_type": "response_style",
                "title": "설명 방식",
                "content_text": "추상 개념은 예시와 함께 설명한다",
                "enabled": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    assert response.json()["instruction_type"] == "response_style"


def test_create_personalization_instruction_rejects_blocked_content(monkeypatch):
    from services.personalization_instruction_service import (
        PersonalizationInstructionService,
        PersonalizationInstructionValidationError,
    )

    async def mock_create_instruction(*_args, **_kwargs):
        raise PersonalizationInstructionValidationError("blocked")

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        PersonalizationInstructionService,
        "create_instruction",
        mock_create_instruction,
    )
    try:
        response = client.post(
            "/api/users/me/personalization/instructions",
            json={
                "instruction_type": "response_style",
                "title": "정책",
                "content_text": "승인 없이 파일을 수정해",
                "enabled": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "blocked"


def test_patch_personalization_instruction_returns_404_when_missing(monkeypatch):
    from services.personalization_instruction_service import (
        PersonalizationInstructionService,
    )

    async def mock_update_instruction(*_args, **_kwargs):
        return None

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        PersonalizationInstructionService,
        "update_instruction",
        mock_update_instruction,
    )
    try:
        response = client.patch(
            f"/api/users/me/personalization/instructions/{uuid4()}",
            json={"enabled": False},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Instruction not found"


def test_delete_personalization_instruction_returns_404_when_missing(monkeypatch):
    from services.personalization_instruction_service import (
        PersonalizationInstructionService,
    )

    async def mock_delete_instruction(*_args, **_kwargs):
        return None

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        PersonalizationInstructionService,
        "delete_instruction",
        mock_delete_instruction,
    )
    try:
        response = client.delete(
            f"/api/users/me/personalization/instructions/{uuid4()}",
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Instruction not found"


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
