import json
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from schemas.chat import ChatRequest
from workflow.main_graph import get_orchagent_graph
from core.database import get_db
from core.config import settings
from services.trace_service import TraceService

router = APIRouter()

@router.post("/chat")
async def chat_stream(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Streaming endpoint for chat with persistence and tracing."""
    
    async def event_generator():
        inputs = {"messages": [("user", request.message)]}
        config = {"configurable": {"thread_id": request.thread_id}}
        
        try:
            async with AsyncPostgresSaver.from_conn_string(settings.async_database_uri) as checkpointer:
                # 1. Setup checkpointer once
                await checkpointer.setup()
                
                # 2. Compile graph with checkpointer
                builder = get_orchagent_graph()
                graph = builder.compile(checkpointer=checkpointer)
                
                # 3. Stream events
                async for event in graph.astream_events(inputs, config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "unknown")
                    
                    payload = {
                        "event_type": kind,
                        "node": name,
                        "data": str(event.get("data", {}))
                    }
                    
                    # 4. Save trace using TraceService
                    await TraceService.create_event(
                        db=db,
                        thread_id=request.thread_id,
                        event_type=kind,
                        node_name=name,
                        payload=payload
                    )
                    
                    yield {
                        "event": "message",
                        "data": json.dumps(payload)
                    }
                    
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
            
    return EventSourceResponse(event_generator())

@router.get("/thread/{thread_id}/trace")
async def get_thread_trace(thread_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve execution trace for a specific thread."""
    traces = await TraceService.get_thread_traces(db, thread_id)
    return {"thread_id": thread_id, "traces": traces}
