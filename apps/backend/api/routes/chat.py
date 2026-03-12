import json
import sys
from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.errors import GraphInterrupt

from schemas.chat import ChatRequest, ResumeRequest
from workflow.main_graph import get_orchagent_graph
from core.database import get_db
from core.config import settings
from services.trace_service import TraceService
from services.logging_service import LoggingService
from services.file_logger import JsonLogger
from services.storage_service import StorageService

router = APIRouter()


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _display_name(name: str | None) -> str | None:
    if not name:
        return None

    if name == "head_supervisor":
        return "Head Supervisor"
    if name == "supervisor":
        return "Team Supervisor"
    if name == "FINISH":
        return "Completed"
    if name.endswith("_team"):
        base = " ".join(part.capitalize() for part in name[: -len("_team")].split("_"))
        return f"{base} Team"

    parts = name.replace("_team", "").replace("_", " ").split()
    return " ".join(part.capitalize() for part in parts)


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(v) for v in value]

    if hasattr(value, "model_dump"):
        return _serialize_value(value.model_dump())

    if hasattr(value, "dict"):
        return _serialize_value(value.dict())

    if hasattr(value, "content"):
        return {
            "type": getattr(value, "type", value.__class__.__name__),
            "name": getattr(value, "name", None),
            "content": _serialize_value(getattr(value, "content", None)),
            "additional_kwargs": _serialize_value(
                getattr(value, "additional_kwargs", None)
            ),
        }

    return repr(value)


def _extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "content" in item:
                    parts.append(_extract_text_content(item["content"]))
        return "".join(parts)
    return str(content)


def _extract_reasoning_chunk(chunk: Any) -> str:
    additional_kwargs = getattr(chunk, "additional_kwargs", {}) or {}
    return (
        additional_kwargs.get("reasoning_summary_text")
        or additional_kwargs.get("reasoning_content")
        or ""
    )


def _chunk_text(text: str, chunk_size: int = 24) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _trace_event(thread_id: str, payload: dict[str, Any]):
    return TraceService.build_event(
        thread_id=thread_id,
        event_type=payload["event_type"],
        node_name=payload.get("node"),
        payload=payload,
    )


def _status_payload(
    *,
    status: str,
    thread_id: str,
    node: str | None,
    message: str,
    active_team: str | None = None,
    active_worker: str | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "status",
        "status": status,
        "thread_id": thread_id,
        "node": node,
        "display_name": _display_name(active_worker or active_team or node),
        "active_team": active_team,
        "active_worker": active_worker,
        "message": message,
        "timestamp": _utc_timestamp(),
    }


def _route_payload(node: str, route_entry: dict[str, Any]) -> dict[str, Any]:
    target = route_entry.get("next")
    display_target = route_entry.get("worker") or target or route_entry.get("team")
    return {
        "event_type": "route",
        "node": node,
        "layer": route_entry.get("layer"),
        "source": route_entry.get("node"),
        "target": target,
        "team": route_entry.get("team"),
        "worker": route_entry.get("worker"),
        "status": route_entry.get("status"),
        "display_name": _display_name(display_target),
        "timestamp": _utc_timestamp(),
    }


async def _build_checkpoint_payload(graph: Any, config: dict[str, Any], thread_id: str):
    snapshot = await graph.aget_state(config, subgraphs=True)
    configurable = snapshot.config.get("configurable", {})
    state_values = snapshot.values if isinstance(snapshot.values, dict) else {}

    return {
        "event_type": "checkpoint",
        "thread_id": thread_id,
        "node": "checkpoint",
        "checkpoint_id": configurable.get("checkpoint_id"),
        "checkpoint_ns": configurable.get("checkpoint_ns"),
        "created_at": snapshot.created_at,
        "next_nodes": list(snapshot.next),
        "active_team": state_values.get("active_team"),
        "active_worker": state_values.get("active_worker"),
        "streaming_status": state_values.get("streaming_status"),
        "message_count": len(state_values.get("messages", [])),
        "route_history_length": len(state_values.get("route_history", [])),
        "timestamp": _utc_timestamp(),
    }


@router.post("/chat")
async def chat_stream(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Streaming endpoint for chat with persistence and tracing."""
    print(
        f"[Chat] Endpoint called! thread_id={request.thread_id}",
        file=sys.stderr,
        flush=True,
    )

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
        final_answer_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        trace_events = []
        graph = None
        completed_payload_emitted = False

        def emit(payload: dict[str, Any], *, persist: bool = True):
            if persist:
                trace_events.append(_trace_event(request.thread_id, payload))
            return {"event": "message", "data": json.dumps(payload)}

        try:
            yield emit(
                _status_payload(
                    status="running",
                    thread_id=request.thread_id,
                    node="head_supervisor",
                    message="Coordinating team...",
                )
            )

            async with AsyncPostgresSaver.from_conn_string(
                settings.sync_database_uri
            ) as checkpointer:
                builder = get_orchagent_graph()
                graph = builder.compile(checkpointer=checkpointer)

                async for event in graph.astream_events(inputs, config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "unknown")
                    data = event.get("data", {})
                    run_id = event.get("run_id")

                    if kind == "on_chat_model_stream" and name != "unknown":
                        chunk = data.get("chunk")
                        reasoning_chunk = _extract_reasoning_chunk(chunk)
                        if reasoning_chunk:
                            reasoning_chunks.append(reasoning_chunk)
                            yield emit(
                                {
                                    "event_type": "reasoning",
                                    "node": name,
                                    "display_name": _display_name(name),
                                    "content": reasoning_chunk,
                                    "run_id": run_id,
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )

                        text_chunk = _extract_text_content(
                            getattr(chunk, "content", "")
                        )
                        if text_chunk:
                            final_answer_chunks.append(text_chunk)
                            yield emit(
                                {
                                    "event_type": "text",
                                    "node": name,
                                    "display_name": _display_name(name),
                                    "content": text_chunk,
                                    "run_id": run_id,
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )
                        continue

                    if kind == "on_tool_start":
                        yield emit(
                            {
                                "event_type": "tool_start",
                                "node": name,
                                "tool_name": name,
                                "display_name": _display_name(name),
                                "input": _serialize_value(data.get("input")),
                                "run_id": run_id,
                                "timestamp": _utc_timestamp(),
                            }
                        )
                        continue

                    if kind == "on_tool_end":
                        yield emit(
                            {
                                "event_type": "tool_end",
                                "node": name,
                                "tool_name": name,
                                "display_name": _display_name(name),
                                "output": _serialize_value(data.get("output")),
                                "run_id": run_id,
                                "timestamp": _utc_timestamp(),
                            }
                        )
                        continue

                    if kind == "on_tool_error":
                        yield emit(
                            {
                                "event_type": "tool_error",
                                "node": name,
                                "tool_name": name,
                                "display_name": _display_name(name),
                                "error": _serialize_value(data.get("error")),
                                "run_id": run_id,
                                "timestamp": _utc_timestamp(),
                            }
                        )
                        continue

                    if kind == "on_chain_end":
                        output = data.get("output")
                        if isinstance(output, Command):
                            update = output.update or {}
                            route_history = update.get("route_history") or []
                            if route_history:
                                yield emit(_route_payload(name, route_history[-1]))

                            if name == "head_supervisor":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield emit(
                                        _status_payload(
                                            status=status,
                                            thread_id=request.thread_id,
                                            node=name,
                                            active_team=update.get("active_team"),
                                            active_worker=update.get("active_worker"),
                                            message=(
                                                "Completed"
                                                if status == "completed"
                                                else "Delegating to next team..."
                                            ),
                                        )
                                    )

                                direct_messages = update.get("messages") or []
                                if direct_messages:
                                    content_str = _extract_text_content(
                                        getattr(direct_messages[-1], "content", "")
                                    )
                                    if content_str and not final_answer_chunks:
                                        for text_chunk in _chunk_text(content_str):
                                            final_answer_chunks.append(text_chunk)
                                            yield emit(
                                                {
                                                    "event_type": "text",
                                                    "node": name,
                                                    "display_name": _display_name(name),
                                                    "content": text_chunk,
                                                    "timestamp": _utc_timestamp(),
                                                },
                                                persist=False,
                                            )

                checkpoint_payload = await _build_checkpoint_payload(
                    graph, config, request.thread_id
                )
                yield emit(checkpoint_payload)

                if not completed_payload_emitted:
                    yield emit(
                        _status_payload(
                            status="completed",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Completed",
                        )
                    )

                final_answer = "".join(final_answer_chunks)
                if final_answer:
                    await LoggingService.log_message(
                        db, request.thread_id, role="assistant", content=final_answer
                    )

                    JsonLogger.log_session(
                        session_id=request.thread_id,
                        user_id=user_id,
                        event_type="turn_end",
                        metadata={"response_length": len(final_answer)},
                    )
                    JsonLogger.log_usage(
                        user_id=user_id,
                        model="gpt-5.4-2026-03-05",
                        prompt_tokens=len(request.message) // 4,
                        completion_tokens=len(final_answer) // 4,
                    )

        except GraphInterrupt as gi:
            print(f"[Chat] Graph interrupted: {gi}", file=sys.stderr, flush=True)
            yield emit(
                _status_payload(
                    status="interrupted",
                    thread_id=request.thread_id,
                    node="OrchAgent",
                    message="Requires user action.",
                )
            )
        except Exception as e:
            yield emit(
                _status_payload(
                    status="errored",
                    thread_id=request.thread_id,
                    node="OrchAgent",
                    message="Execution failed.",
                )
            )
            yield emit(
                {
                    "event_type": "error",
                    "node": "OrchAgent",
                    "message": str(e),
                    "timestamp": _utc_timestamp(),
                }
            )
        finally:
            if reasoning_chunks:
                trace_events.append(
                    _trace_event(
                        request.thread_id,
                        {
                            "event_type": "reasoning_summary",
                            "node": "assistant",
                            "content": "".join(reasoning_chunks),
                            "timestamp": _utc_timestamp(),
                        },
                    )
                )
            if final_answer_chunks:
                trace_events.append(
                    _trace_event(
                        request.thread_id,
                        {
                            "event_type": "text_summary",
                            "node": "assistant",
                            "content": "".join(final_answer_chunks),
                            "timestamp": _utc_timestamp(),
                        },
                    )
                )

            if trace_events:
                try:
                    await TraceService.create_events(db, trace_events)
                except Exception as trace_error:
                    print(
                        f"[Chat] Failed to persist trace batch: {trace_error}",
                        file=sys.stderr,
                        flush=True,
                    )

    return EventSourceResponse(event_generator())


@router.post("/chat/resume")
async def chat_resume_stream(
    request: ResumeRequest, db: AsyncSession = Depends(get_db)
):
    """Streaming endpoint to resume an interrupted graph."""
    print(
        f"[Chat] Resume Endpoint called! thread_id={request.thread_id}, action={request.action}",
        file=sys.stderr,
        flush=True,
    )

    user_id = "anonymous_user"

    # 1. DB Logging
    resume_message = f"[User Action]: {request.action}"
    if request.feedback:
        resume_message += f"\nFeedback: {request.feedback}"

    await LoggingService.log_message(
        db, request.thread_id, role="user", content=resume_message
    )

    JsonLogger.log_session(
        session_id=request.thread_id,
        user_id=user_id,
        event_type="resume_start",
        metadata={
            "action": request.action,
            "has_feedback": bool(request.feedback),
        },
    )

    async def event_generator():
        # Command input with resume
        command = Command(
            resume={"action": request.action, "feedback": request.feedback}
        )
        config = {"configurable": {"thread_id": request.thread_id}}

        final_answer_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        trace_events = []
        graph = None
        completed_payload_emitted = False

        def emit(payload: dict[str, Any], *, persist: bool = True):
            if persist:
                trace_events.append(_trace_event(request.thread_id, payload))
            return {"event": "message", "data": json.dumps(payload)}

        try:
            yield emit(
                _status_payload(
                    status="running",
                    thread_id=request.thread_id,
                    node="head_supervisor",
                    message="Resuming graph execution...",
                )
            )

            async with AsyncPostgresSaver.from_conn_string(
                settings.sync_database_uri
            ) as checkpointer:
                builder = get_orchagent_graph()
                graph = builder.compile(checkpointer=checkpointer)

                async for event in graph.astream_events(command, config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "unknown")
                    data = event.get("data", {})
                    run_id = event.get("run_id")

                    if kind == "on_chat_model_stream" and name != "unknown":
                        chunk = data.get("chunk")
                        reasoning_chunk = _extract_reasoning_chunk(chunk)
                        if reasoning_chunk:
                            reasoning_chunks.append(reasoning_chunk)
                            yield emit(
                                {
                                    "event_type": "reasoning",
                                    "node": name,
                                    "display_name": _display_name(name),
                                    "content": reasoning_chunk,
                                    "run_id": run_id,
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )

                        text_chunk = _extract_text_content(
                            getattr(chunk, "content", "")
                        )
                        if text_chunk:
                            final_answer_chunks.append(text_chunk)
                            yield emit(
                                {
                                    "event_type": "text",
                                    "node": name,
                                    "display_name": _display_name(name),
                                    "content": text_chunk,
                                    "run_id": run_id,
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )
                        continue

                    if kind == "on_tool_start":
                        yield emit(
                            {
                                "event_type": "tool_start",
                                "node": name,
                                "tool_name": name,
                                "display_name": _display_name(name),
                                "input": _serialize_value(data.get("input")),
                                "run_id": run_id,
                                "timestamp": _utc_timestamp(),
                            }
                        )
                        continue

                    if kind == "on_tool_end":
                        yield emit(
                            {
                                "event_type": "tool_end",
                                "node": name,
                                "tool_name": name,
                                "display_name": _display_name(name),
                                "output": _serialize_value(data.get("output")),
                                "run_id": run_id,
                                "timestamp": _utc_timestamp(),
                            }
                        )
                        continue

                    if kind == "on_tool_error":
                        yield emit(
                            {
                                "event_type": "tool_error",
                                "node": name,
                                "tool_name": name,
                                "display_name": _display_name(name),
                                "error": _serialize_value(data.get("error")),
                                "run_id": run_id,
                                "timestamp": _utc_timestamp(),
                            }
                        )
                        continue

                    if kind == "on_chain_end":
                        output = data.get("output")
                        if isinstance(output, Command):
                            update = output.update or {}
                            route_history = update.get("route_history") or []
                            if route_history:
                                yield emit(_route_payload(name, route_history[-1]))

                            if name == "head_supervisor":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield emit(
                                        _status_payload(
                                            status=status,
                                            thread_id=request.thread_id,
                                            node=name,
                                            active_team=update.get("active_team"),
                                            active_worker=update.get("active_worker"),
                                            message=(
                                                "Completed"
                                                if status == "completed"
                                                else "Delegating to next team..."
                                            ),
                                        )
                                    )

                                direct_messages = update.get("messages") or []
                                if direct_messages:
                                    content_str = _extract_text_content(
                                        getattr(direct_messages[-1], "content", "")
                                    )
                                    if content_str and not final_answer_chunks:
                                        for text_chunk in _chunk_text(content_str):
                                            final_answer_chunks.append(text_chunk)
                                            yield emit(
                                                {
                                                    "event_type": "text",
                                                    "node": name,
                                                    "display_name": _display_name(name),
                                                    "content": text_chunk,
                                                    "timestamp": _utc_timestamp(),
                                                },
                                                persist=False,
                                            )

                checkpoint_payload = await _build_checkpoint_payload(
                    graph, config, request.thread_id
                )
                yield emit(checkpoint_payload)

                if not completed_payload_emitted:
                    yield emit(
                        _status_payload(
                            status="completed",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Completed",
                        )
                    )

                final_answer = "".join(final_answer_chunks)
                if final_answer:
                    await LoggingService.log_message(
                        db, request.thread_id, role="assistant", content=final_answer
                    )

                    JsonLogger.log_session(
                        session_id=request.thread_id,
                        user_id=user_id,
                        event_type="turn_end",
                        metadata={"response_length": len(final_answer)},
                    )

        except GraphInterrupt as gi:
            print(f"[Chat] Graph interrupted again: {gi}", file=sys.stderr, flush=True)
            yield emit(
                _status_payload(
                    status="interrupted",
                    thread_id=request.thread_id,
                    node="OrchAgent",
                    message="Requires user action.",
                )
            )
        except Exception as e:
            yield emit(
                _status_payload(
                    status="errored",
                    thread_id=request.thread_id,
                    node="OrchAgent",
                    message="Execution failed.",
                )
            )
            yield emit(
                {
                    "event_type": "error",
                    "node": "OrchAgent",
                    "message": str(e),
                    "timestamp": _utc_timestamp(),
                }
            )
        finally:
            if reasoning_chunks:
                trace_events.append(
                    _trace_event(
                        request.thread_id,
                        {
                            "event_type": "reasoning_summary",
                            "node": "assistant",
                            "content": "".join(reasoning_chunks),
                            "timestamp": _utc_timestamp(),
                        },
                    )
                )
            if final_answer_chunks:
                trace_events.append(
                    _trace_event(
                        request.thread_id,
                        {
                            "event_type": "text_summary",
                            "node": "assistant",
                            "content": "".join(final_answer_chunks),
                            "timestamp": _utc_timestamp(),
                        },
                    )
                )

            if trace_events:
                try:
                    await TraceService.create_events(db, trace_events)
                except Exception as trace_error:
                    print(
                        f"[Chat] Failed to persist trace batch: {trace_error}",
                        file=sys.stderr,
                        flush=True,
                    )

    return EventSourceResponse(event_generator())


@router.get("/thread/{thread_id}/trace")
async def get_thread_trace(thread_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve execution trace for a specific thread."""
    traces = await TraceService.get_thread_traces(db, thread_id)
    return {"thread_id": thread_id, "traces": traces}
