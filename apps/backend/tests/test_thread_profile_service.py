from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from models.thread_profile import ThreadProfile
from services.thread_profile_service import ThreadProfileService


def test_normalize_title_collapses_and_trims():
    assert ThreadProfileService.normalize_title("  hello   world  ") == "hello world"
    assert ThreadProfileService.normalize_title("   ") is None


@pytest.mark.asyncio
async def test_upsert_thread_profile_creates_profile(monkeypatch):
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def mock_get_thread_profile(*args, **kwargs):
        return None

    monkeypatch.setattr(
        ThreadProfileService,
        "get_thread_profile",
        mock_get_thread_profile,
    )

    profile = await ThreadProfileService.upsert_thread_profile(
        db,
        thread_id="thread-1",
        user_id="user-1",
        title="  renamed title ",
        pinned=True,
    )

    assert isinstance(profile, ThreadProfile)
    assert profile.title_override == "renamed title"
    assert profile.pinned is True
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(profile)


@pytest.mark.asyncio
async def test_set_generated_title_if_missing_skips_existing_override(monkeypatch):
    existing = ThreadProfile(thread_id="thread-1", user_id="user-1", title_override="Manual")
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def mock_get_thread_profile(*args, **kwargs):
        return existing

    monkeypatch.setattr(
        ThreadProfileService,
        "get_thread_profile",
        mock_get_thread_profile,
    )

    profile = await ThreadProfileService.set_generated_title_if_missing(
        db,
        thread_id="thread-1",
        user_id="user-1",
        title="AI title",
    )

    assert profile.title_override == "Manual"
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()
