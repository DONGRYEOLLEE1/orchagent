from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import engine, Base
from api.routes import chat, health

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create DB tables for tracing if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Setup LangGraph checkpointer tables once at startup
    # Use standard postgresql:// (psycopg handles async internally)
    async with AsyncPostgresSaver.from_conn_string(settings.sync_database_uri) as checkpointer:
        await checkpointer.setup()
        
    yield
    # Cleanup on shutdown
    await engine.dispose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="OrchAgent Hierarchical Agent Backend API",
    lifespan=lifespan
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix=settings.API_V1_STR, tags=["chat"])
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["health"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
