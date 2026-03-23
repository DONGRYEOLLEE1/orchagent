from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.auth import AuthUser
from services.auth_service import DuplicateEmailError


class UserProfileService:
    @staticmethod
    def normalize_display_name(display_name: str | None) -> str | None:
        if display_name is None:
            return None
        normalized = display_name.strip()
        return normalized or None

    @staticmethod
    def normalize_email(email: str | None) -> str | None:
        if email is None:
            return None
        normalized = email.strip().lower()
        return normalized or None

    @staticmethod
    async def patch_self(
        db: AsyncSession,
        *,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> AuthUser:
        result = await db.execute(select(AuthUser).where(AuthUser.id == user_id))
        user = result.scalar_one()

        normalized_display_name = UserProfileService.normalize_display_name(display_name)
        normalized_email = UserProfileService.normalize_email(email)

        if email is not None:
            if normalized_email is None:
                user.email = None
            else:
                existing_email = await db.execute(
                    select(AuthUser).where(
                        AuthUser.email == normalized_email,
                        AuthUser.id != user_id,
                    )
                )
                if existing_email.scalar_one_or_none() is not None:
                    raise DuplicateEmailError("Email is already in use.")
                user.email = normalized_email

        if display_name is not None:
            user.display_name = normalized_display_name

        await db.commit()
        await db.refresh(user)
        return user
