from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.thread_profile import ThreadProfile


class ThreadProfileService:
    @staticmethod
    def normalize_title(title: str | None) -> str | None:
        if title is None:
            return None
        normalized = " ".join(title.split()).strip()
        return normalized or None

    @staticmethod
    async def get_thread_profile(
        db: AsyncSession, thread_id: str, user_id: str
    ) -> ThreadProfile | None:
        result = await db.execute(
            select(ThreadProfile).where(
                ThreadProfile.thread_id == thread_id,
                ThreadProfile.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_thread_profiles_map(
        db: AsyncSession, thread_ids: list[str], user_id: str
    ) -> dict[str, ThreadProfile]:
        if not thread_ids:
            return {}

        result = await db.execute(
            select(ThreadProfile).where(
                ThreadProfile.thread_id.in_(thread_ids),
                ThreadProfile.user_id == user_id,
            )
        )
        profiles = result.scalars().all()
        return {profile.thread_id: profile for profile in profiles}

    @staticmethod
    async def upsert_thread_profile(
        db: AsyncSession,
        *,
        thread_id: str,
        user_id: str,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> ThreadProfile:
        profile = await ThreadProfileService.get_thread_profile(db, thread_id, user_id)
        if profile is None:
            profile = ThreadProfile(thread_id=thread_id, user_id=user_id)
            db.add(profile)

        normalized_title = ThreadProfileService.normalize_title(title)
        if title is not None:
            profile.title_override = normalized_title
        if pinned is not None:
            profile.pinned = pinned
        if archived is not None:
            profile.archived = archived

        await db.commit()
        await db.refresh(profile)
        return profile
