from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.auth import AuthUser


class AdminUserService:
    @staticmethod
    async def patch_user_status(
        db: AsyncSession,
        *,
        actor_user_id: str,
        target_user_id: str,
        status: str,
    ) -> AuthUser:
        result = await db.execute(select(AuthUser).where(AuthUser.id == target_user_id))
        target_user = result.scalar_one()

        if actor_user_id == target_user_id and status == "disabled":
            raise ValueError("Admins cannot disable their own account.")

        target_user.status = status
        await db.commit()
        await db.refresh(target_user)
        return target_user
