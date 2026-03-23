from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.auth import AuthUser
from services.auth_service import DuplicateEmailError, hash_password
from services.user_profile_service import UserProfileService


def test_normalize_profile_fields():
    assert UserProfileService.normalize_display_name("  Dr. Lee  ") == "Dr. Lee"
    assert UserProfileService.normalize_email("  USER@Example.com ") == "user@example.com"


@pytest.mark.asyncio
async def test_patch_self_raises_on_duplicate_email():
    user = AuthUser(
        id="user-1",
        login_id="user1",
        password_hash=hash_password("abcdefghijklmn1"),
    )

    results = iter(
        [
            SimpleNamespace(scalar_one=lambda: user),
            SimpleNamespace(scalar_one_or_none=lambda: object()),
        ]
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=lambda *args, **kwargs: next(results))

    with pytest.raises(DuplicateEmailError):
        await UserProfileService.patch_self(
            db,
            user_id="user-1",
            email="dup@example.com",
        )
