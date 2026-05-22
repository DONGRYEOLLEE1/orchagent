from unittest.mock import AsyncMock, Mock

import pytest

from models.thread_profile import ThreadProfile
from services.thread_profile_service import ThreadProfileService


@pytest.mark.asyncio
async def test_set_generated_title_if_missing_skips_existing_override(monkeypatch):
    """Generated title must not clobber a manual user-set title."""
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
