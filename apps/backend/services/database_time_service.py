from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DatabaseTimeService:
    @staticmethod
    async def ensure_kst_timezone(db: AsyncSession) -> None:
        await db.execute(text("ALTER DATABASE orchagent SET timezone TO 'Asia/Seoul'"))
        await db.execute(text("ALTER ROLE postgres SET timezone TO 'Asia/Seoul'"))
        await db.execute(text("SET TIME ZONE 'Asia/Seoul'"))
        await db.commit()
