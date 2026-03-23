from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.auth import AuthUser
from services.auth_service import hash_password
from services.admin_user_service import AdminUserService


@pytest.mark.asyncio
async def test_patch_user_status_blocks_self_disable():
    target_user = AuthUser(
        id="admin-1",
        login_id="admin",
        password_hash=hash_password("adminpassword7x"),
        role="admin",
        status="active",
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: target_user))

    with pytest.raises(ValueError):
        await AdminUserService.patch_user_status(
            db,
            actor_user_id="admin-1",
            target_user_id="admin-1",
            status="disabled",
        )
