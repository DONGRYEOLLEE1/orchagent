import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import engine, Base, AsyncSessionLocal
from api.routes import auth, chat, health, threads, users
import models  # noqa: F401

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from services.auth_service import ensure_bootstrap_admin
from services.llm_pricing_service import LLMPricingService

logger = logging.getLogger(__name__)


async def _initialize_runtime_dependencies_once() -> None:
    # 1. Create DB tables for tracing if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Setup LangGraph checkpointer tables once at startup
    # Use standard postgresql:// (psycopg handles async internally)
    async with AsyncPostgresSaver.from_conn_string(
        settings.sync_database_uri
    ) as checkpointer:
        await checkpointer.setup()

    async with AsyncSessionLocal() as db:
        await ensure_bootstrap_admin(db)
        await LLMPricingService.ensure_default_pricing_snapshots(db)


async def initialize_runtime_dependencies() -> None:
    last_error: Exception | None = None

    for attempt in range(1, settings.STARTUP_MAX_RETRIES + 1):
        try:
            await _initialize_runtime_dependencies_once()
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Startup dependency initialization failed (attempt %s/%s): %s",
                attempt,
                settings.STARTUP_MAX_RETRIES,
                exc,
            )
            if attempt == settings.STARTUP_MAX_RETRIES:
                raise
            await asyncio.sleep(settings.STARTUP_RETRY_DELAY_SECONDS)

    if last_error:
        raise last_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_runtime_dependencies()

    yield
    # Cleanup on shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="OrchAgent Hierarchical Agent Backend API",
    lifespan=lifespan,
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,  # type: ignore
    allow_origins=settings.auth_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix=settings.API_V1_STR, tags=["chat"])
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(threads.router, prefix=settings.API_V1_STR, tags=["threads"])
app.include_router(users.router, prefix=settings.API_V1_STR, tags=["users"])
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["health"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.BACKEND_PORT, reload=True)
