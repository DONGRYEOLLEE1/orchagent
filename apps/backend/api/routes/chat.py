import json
import sys
from typing import Any
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage

from schemas.chat import ChatRequest
from workflow.main_graph import get_orchagent_graph
from core.database import get_db
from core.config import settings
from services.trace_service import TraceService
from services.logging_service import LoggingService
from services.file_logger import JsonLogger
from services.storage_service import StorageService

router = APIRouter()

@router.post("/chat")
async def chat_stream(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Streaming endpoint for chat with persistence and tracing."""
    print(f"[Chat] Endpoint called! thread_id={request.thread_id}", file=sys.stderr, flush=True)

    # We will use a dummy user_id for now as auth is not yet implemented
    user_id = "anonymous_user"

    # Save images to disk and get paths for logging
    image_paths = []
    if request.images:
        image_paths = [StorageService.save_base64_image(img) for img in request.images]

    # 1. DB Logging
    await LoggingService.log_message(
        db, request.thread_id, role="user", content=request.message
    )

    # 2. File Logging (Session start/turn)
    JsonLogger.log_session(
        session_id=request.thread_id,
        user_id=user_id,
        event_type="turn_start",
        metadata={
            "message_length": len(request.message),
            "has_images": bool(request.images),
            "image_paths": image_paths,
        },
    )

    async def event_generator():
        # Construct multimodal message if images are present
        if request.images:
            content: list[Any] = [{"type": "text", "text": request.message}]
            for img in request.images:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img}"},
                    }
                )
            inputs = {"messages": [HumanMessage(content=content)]}
        else:
            inputs = {"messages": [("user", request.message)]}

        config = {"configurable": {"thread_id": request.thread_id}}
        final_answer = ""

        try:
            async with AsyncPostgresSaver.from_conn_string(
                settings.sync_database_uri
            ) as checkpointer:
                # 1. Setup checkpointer once (Handled by lifespan in main.py now)
                # await checkpointer.setup()

                # 2. Compile graph with checkpointer
                builder = get_orchagent_graph()
                graph = builder.compile(checkpointer=checkpointer)

                # 3. Stream events
                async for event in graph.astream_events(inputs, config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "unknown")

                    # Capture assistant output and reasoning summaries
                    if kind == "on_chat_model_stream" and name != "unknown":
                        chunk = event.get("data", {}).get("chunk")

                        # 1. Capture reasoning summary if available
                        reasoning_chunk = getattr(chunk, "additional_kwargs", {}).get(
                            "reasoning_summary_text"
                        ) or getattr(chunk, "additional_kwargs", {}).get(
                            "reasoning_content"
                        )
                        if reasoning_chunk:
                            yield {
                                "event": "message",
                                "data": json.dumps(
                                    {
                                        "event_type": "reasoning",
                                        "node": name,
                                        "content": reasoning_chunk,
                                    }
                                ),
                            }

                        # 2. Capture final answer content
                        if (
                            chunk
                            and hasattr(chunk, "content")
                            and isinstance(chunk.content, str)
                        ):
                            final_answer += chunk.content

                    # Capture direct response from Supervisor (Non-streaming)
                    if kind == "on_chain_end" and name == "head_supervisor":
                        from langgraph.types import Command
                        import asyncio
                        output = event.get("data", {}).get("output")
                        if isinstance(output, Command) and "messages" in output.update:
                            msg = output.update["messages"][0]
                            if hasattr(msg, "content") and msg.content:
                                # Split the content to simulate streaming
                                content_str = str(msg.content)
                                # Smaller chunk size and random-like delay for natural feel
                                chunk_size = 2 # 2 characters at a time
                                for i in range(0, len(content_str), chunk_size):
                                    chunk = content_str[i:i+chunk_size]
                                    yield {
                                        "event": "message",
                                        "data": json.dumps(
                                            {
                                                "event_type": "text",
                                                "node": name,
                                                "content": chunk,
                                            }
                                        ),
                                    }
                                    await asyncio.sleep(0.04) # Slower for more natural feel (approx 25-50 tokens/sec)
                                final_answer += content_str

                    payload = {
                        "event_type": kind,
                        "node": name,
                        "data": str(event.get("data", {})),
                    }

                    # 4. Save raw trace using TraceService
                    await TraceService.create_event(
                        db=db,
                        thread_id=request.thread_id,
                        event_type=kind,
                        node_name=name,
                        payload=payload,
                    )

                    yield {"event": "message", "data": json.dumps(payload)}

                # Log final AI Response
                if final_answer:
                    await LoggingService.log_message(
                        db, request.thread_id, role="assistant", content=final_answer
                    )

                    # File Logging (Session end)
                    JsonLogger.log_session(
                        session_id=request.thread_id,
                        user_id=user_id,
                        event_type="turn_end",
                        metadata={"response_length": len(final_answer)},
                    )
                    # Dummy token usage tracking
                    JsonLogger.log_usage(
                        user_id=user_id,
                        model="gpt-5.4-2026-03-05",
                        prompt_tokens=len(request.message) // 4,
                        completion_tokens=len(final_answer) // 4,
                    )

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_generator())

@router.get("/thread/{thread_id}/trace")
async def get_thread_trace(thread_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve execution trace for a specific thread."""
    traces = await TraceService.get_thread_traces(db, thread_id)
    return {"thread_id": thread_id, "traces": traces}
