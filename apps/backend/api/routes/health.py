from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from core.database import engine

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "message": "OrchAgent backend is running."}


@router.get("/health/ready")
async def readiness_check():
    """Readiness check that verifies the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "checks": {"database": "error"},
                "detail": str(exc),
            },
        )

    return {
        "status": "ok",
        "checks": {"database": "ok"},
    }
