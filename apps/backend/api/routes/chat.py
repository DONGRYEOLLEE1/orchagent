import json
import re
import sys
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.errors import GraphInterrupt

from agent_core.supervisor import requires_human_approval_for_text
from schemas.chat import ChatRequest, ResumeRequest
from workflow.main_graph import DEFAULT_LLM_MODEL, get_orchagent_graph
from core.database import AsyncSessionLocal, get_db
from core.config import settings
from services.security_service import get_current_user, require_csrf
from services.thread_service import ThreadService
from services.trace_service import TraceService
from services.logging_service import LoggingService
from services.file_logger import JsonLogger
from services.storage_service import StorageService

router = APIRouter()
FINAL_TEXT_STREAM_NODES = {"head_supervisor", "finalizer"}
INTERNAL_MESSAGE_NAMES = {"planner", "supervisor", "reviewer", "validator"}


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


def _event_node_name(event: dict[str, Any]) -> str:
    metadata = event.get("metadata") or {}
    return metadata.get("langgraph_node") or event.get("name", "unknown")


def _parse_json_string(value: str) -> str:
    return json.loads(f'"{value}"')


def _extract_final_supervisor_content_text(
    text_chunk: str, state: dict[str, Any]
) -> str:
    if not text_chunk and not (
        state.get("content_done")
        and state.get("next_parsed")
        and state.get("next_value") == "FINISH"
        and state.get("pending_content")
    ):
        return ""

    if state.get("content_done") and state.get("next_parsed"):
        pending_content = state.get("pending_content", "")
        if state.get("next_value") == "FINISH" and pending_content:
            state["pending_content"] = ""
            return pending_content
        state["pending_content"] = ""
        return ""

    raw_buffer = state.get("raw_buffer", "") + text_chunk
    state["raw_buffer"] = raw_buffer

    if not state.get("next_parsed"):
        next_match = re.search(r'"next"\s*:\s*"((?:\\.|[^"])*)"', raw_buffer)
        if next_match:
            state["next_parsed"] = True
            state["next_value"] = _parse_json_string(next_match.group(1))

    if state.get("content_scan_pos") is None:
        # Flexible marker search to handle optional space after colon
        marker_match = re.search(r'"content"\s*:\s*"', raw_buffer)
        if marker_match:
            state["content_scan_pos"] = marker_match.end()

    scan_pos = state.get("content_scan_pos")
    if scan_pos is None:
        return ""

    emitted: list[str] = []
    pending_content = state.get("pending_content", "")
    escape_next = state.get("escape_next", False)

    while scan_pos < len(raw_buffer):
        char = raw_buffer[scan_pos]
        scan_pos += 1

        if escape_next:
            decoded_char = {
                "n": "\n",
                "r": "\r",
                "t": "\t",
                '"': '"',
                "\\": "\\",
            }.get(char, char)
            if state.get("next_parsed") and state.get("next_value") == "FINISH":
                emitted.append(decoded_char)
            else:
                pending_content += decoded_char
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"':
            state["content_done"] = True
            break

        if state.get("next_parsed") and state.get("next_value") == "FINISH":
            emitted.append(char)
        else:
            pending_content += char

    state["content_scan_pos"] = scan_pos
    state["escape_next"] = escape_next

    if state.get("next_parsed"):
        if state.get("next_value") == "FINISH":
            if pending_content:
                emitted.insert(0, pending_content)
                pending_content = ""
        else:
            pending_content = ""

    state["pending_content"] = pending_content
    return "".join(emitted)


def _normalize_model_text_chunk(
    event: dict[str, Any],
    text_chunk: str,
    structured_content_states: dict[str, dict[str, Any]],
) -> str:
    if not text_chunk:
        return ""

    node_name = _event_node_name(event)
    if node_name in FINAL_TEXT_STREAM_NODES:
        run_id = event.get("run_id") or node_name
        state = structured_content_states.setdefault(run_id, {})
        if node_name == "finalizer":
            state.setdefault("next_parsed", True)
            state.setdefault("next_value", "FINISH")
        return _extract_final_supervisor_content_text(text_chunk, state)
    return ""


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


def _extract_final_message_from_state(state_values: dict[str, Any]) -> str:
    messages = state_values.get("messages", [])
    for message in reversed(messages):
        message_type = getattr(message, "type", "")
        if message_type not in {"ai", "assistant"}:
            continue

        message_name = getattr(message, "name", None)
        if message_name in INTERNAL_MESSAGE_NAMES or (
            isinstance(message_name, str) and message_name.endswith("_reviewer")
        ):
            continue

        content = _extract_text_content(getattr(message, "content", ""))
        stripped = content.strip()
        if not stripped:
            continue
        if stripped.startswith("**[Planner]"):
            continue
        if stripped.startswith("[Review "):
            continue
        if stripped == "FINISH":
            continue
        return content

    return ""


@dataclass
class _FinalTextEmission:
    node: str
    content: str
    run_id: str | None = None


@dataclass
class _BufferedFinalTextRun:
    run_id: str
    node: str
    chunks: list[str] = field(default_factory=list)


class _FinalResponseCollector:
    def __init__(self):
        self.final_answer_chunks: list[str] = []
        self.structured_content_states: dict[str, dict[str, Any]] = {}
        self._pending_by_node: dict[str, list[_BufferedFinalTextRun]] = {
            "head_supervisor": []
        }
        self.approved_owner_run_id: str | None = None
        self.approved_owner_node: str | None = None

    def ingest_model_stream(
        self,
        event: dict[str, Any],
        text_chunk: str,
    ) -> list[_FinalTextEmission]:
        normalized_text_chunk = _normalize_model_text_chunk(
            event, text_chunk, self.structured_content_states
        )
        if not normalized_text_chunk:
            return []

        node_name = _event_node_name(event)
        run_id = event.get("run_id") or node_name

        if node_name == "head_supervisor":
            pending_runs = self._pending_by_node.setdefault(node_name, [])
            if pending_runs and pending_runs[-1].run_id == run_id:
                pending_runs[-1].chunks.append(normalized_text_chunk)
            else:
                pending_runs.append(
                    _BufferedFinalTextRun(
                        run_id=run_id,
                        node=node_name,
                        chunks=[normalized_text_chunk],
                    )
                )
            return []

        if node_name == "finalizer":
            return self._approve_chunks(
                node=node_name,
                run_id=run_id,
                chunks=[normalized_text_chunk],
            )

        return []

    def consume_head_supervisor_end(
        self,
        update: dict[str, Any],
        *,
        goto: Any = None,
    ) -> list[_FinalTextEmission]:
        pending_run = self._consume_pending_run("head_supervisor")
        route_history = update.get("route_history") or []
        route_target = route_history[-1].get("next") if route_history else None
        status = update.get("streaming_status")
        response_mode = update.get("response_mode")
        goto_str = str(goto) if goto is not None else None
        is_direct_completion = (
            response_mode == "direct"
            or goto_str == "__end__"
            or (status == "completed" and route_target == "FINISH")
        )

        if not is_direct_completion:
            return []

        if pending_run and pending_run.chunks:
            return self._approve_chunks(
                node=pending_run.node,
                run_id=pending_run.run_id,
                chunks=pending_run.chunks,
            )

        direct_messages = update.get("messages") or []
        if not direct_messages:
            return []

        content_str = _extract_text_content(getattr(direct_messages[-1], "content", ""))
        if not content_str:
            return []

        return self._approve_chunks(
            node="head_supervisor",
            run_id=None,
            chunks=_chunk_text(content_str),
        )

    def consume_finalizer_end(self, update: dict[str, Any]) -> list[_FinalTextEmission]:
        if self.final_answer_chunks:
            return []

        final_messages = update.get("messages") or []
        if not final_messages:
            return []

        content_str = _extract_text_content(getattr(final_messages[-1], "content", ""))
        if not content_str:
            return []

        return self._approve_chunks(
            node="finalizer",
            run_id=None,
            chunks=_chunk_text(content_str),
        )

    def collect_state_fallback(self, state_values: dict[str, Any]) -> list[_FinalTextEmission]:
        if self.final_answer_chunks:
            return []

        fallback_answer = _extract_final_message_from_state(state_values)
        if not fallback_answer:
            return []

        return self._approve_chunks(
            node="assistant",
            run_id=None,
            chunks=_chunk_text(fallback_answer),
        )

    def final_answer(self) -> str:
        return "".join(self.final_answer_chunks)

    def _consume_pending_run(self, node: str) -> _BufferedFinalTextRun | None:
        pending_runs = self._pending_by_node.get(node) or []
        if not pending_runs:
            return None
        return pending_runs.pop(0)

    def _approve_chunks(
        self,
        *,
        node: str,
        run_id: str | None,
        chunks: list[str],
    ) -> list[_FinalTextEmission]:
        if not chunks:
            return []

        approved_run_id = run_id or node
        if self.approved_owner_run_id is None:
            self.approved_owner_run_id = approved_run_id
            self.approved_owner_node = node
        elif self.approved_owner_run_id != approved_run_id:
            return []

        emissions: list[_FinalTextEmission] = []
        for chunk in chunks:
            self.final_answer_chunks.append(chunk)
            emissions.append(
                _FinalTextEmission(node=node, content=chunk, run_id=run_id)
            )
        return emissions


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


def _text_payload_from_emission(emission: _FinalTextEmission) -> dict[str, Any]:
    return {
        "event_type": "text",
        "node": emission.node,
        "display_name": _display_name(emission.node),
        "content": emission.content,
        "run_id": emission.run_id,
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
        "response_mode": state_values.get("response_mode"),
        "streaming_status": state_values.get("streaming_status"),
        "message_count": len(state_values.get("messages", [])),
        "route_history_length": len(state_values.get("route_history", [])),
        "timestamp": _utc_timestamp(),
    }


def _checkpoint_requires_user_action(payload: dict[str, Any]) -> bool:
    next_nodes = payload.get("next_nodes") or []
    streaming_status = payload.get("streaming_status")

    return bool(next_nodes) and streaming_status != "completed"


async def _log_message_with_fresh_session(
    thread_id: str, *, role: str, content: str, user_id: str
) -> None:
    async with AsyncSessionLocal() as db:
        await LoggingService.log_message(
            db, thread_id, role=role, content=content, user_id=user_id
        )


async def _persist_trace_events_with_fresh_session(trace_events: list[Any]) -> None:
    if not trace_events:
        return

    async with AsyncSessionLocal() as db:
        await TraceService.create_events(db, trace_events)


async def _ensure_thread_owned_by_user(
    thread_id: str, user_id: str, *, allow_missing: bool
) -> None:
    async with AsyncSessionLocal() as db:
        session = await ThreadService.get_chat_session(db, thread_id)
        if session is None and allow_missing:
            return
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=404, detail="Thread not found")


def _append_summary_trace_events(
    thread_id: str,
    trace_events: list[Any],
    reasoning_chunks: list[str],
    final_answer_chunks: list[str],
) -> None:
    if reasoning_chunks:
        trace_events.append(
            _trace_event(
                thread_id,
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
                thread_id,
                {
                    "event_type": "text_summary",
                    "node": "assistant",
                    "content": "".join(final_answer_chunks),
                    "timestamp": _utc_timestamp(),
                },
            )
        )


async def _run_cleanup_task(label: str, operation: Any) -> None:
    try:
        await asyncio.shield(operation)
    except asyncio.CancelledError:
        print(
            f"[Chat] Cancelled while waiting for {label}; background cleanup may still continue.",
            file=sys.stderr,
            flush=True,
        )
    except Exception as exc:
        print(f"[Chat] Failed during {label}: {exc}", file=sys.stderr, flush=True)


@router.post("/chat")
async def chat_stream(
    request: ChatRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    """Streaming endpoint for chat with persistence and tracing."""
    print(
        f"[Chat] Endpoint called! thread_id={request.thread_id}",
        file=sys.stderr,
        flush=True,
    )

    user_id = current_user.id

    await _ensure_thread_owned_by_user(
        request.thread_id,
        user_id,
        allow_missing=True,
    )

    # Save images to disk and get paths for logging
    image_paths = []
    if request.images:
        image_paths = [StorageService.save_base64_image(img) for img in request.images]

    # 1. DB Logging
    await _log_message_with_fresh_session(
        request.thread_id, role="user", content=request.message, user_id=user_id
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
        approval_requested = requires_human_approval_for_text(request.message)

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
            inputs = {
                "messages": [HumanMessage(content=content)],
                "shared_context": {
                    "force_requires_approval": approval_requested,
                },
            }
        else:
            inputs = {
                "messages": [("user", request.message)],
                "shared_context": {
                    "force_requires_approval": approval_requested,
                },
            }

        config = {
            "configurable": {"thread_id": request.thread_id},
            "recursion_limit": settings.GRAPH_RECURSION_LIMIT,
        }
        collector = _FinalResponseCollector()
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
                    event_node = _event_node_name(event)
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
                                    "node": event_node,
                                    "display_name": _display_name(event_node),
                                    "content": reasoning_chunk,
                                    "run_id": run_id,
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )

                        text_chunk = _extract_text_content(
                            getattr(chunk, "content", "")
                        )
                        for emission in collector.ingest_model_stream(event, text_chunk):
                            yield emit(
                                _text_payload_from_emission(emission),
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

                                for emission in collector.consume_head_supervisor_end(
                                    update, goto=output.goto
                                ):
                                    yield emit(
                                        _text_payload_from_emission(emission),
                                        persist=False,
                                    )

                            elif name == "finalizer":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield emit(
                                        _status_payload(
                                            status=status,
                                            thread_id=request.thread_id,
                                            node=name,
                                            message="Completed",
                                        )
                                    )
                                for emission in collector.consume_finalizer_end(update):
                                    yield emit(
                                        _text_payload_from_emission(emission),
                                        persist=False,
                                    )

                checkpoint_payload = await _build_checkpoint_payload(
                    graph, config, request.thread_id
                )

                snapshot = await graph.aget_state(config, subgraphs=True)
                state_values = (
                    snapshot.values if isinstance(snapshot.values, dict) else {}
                )
                for emission in collector.collect_state_fallback(state_values):
                    yield emit(
                        _text_payload_from_emission(emission),
                        persist=False,
                    )

                yield emit(checkpoint_payload)

                if _checkpoint_requires_user_action(checkpoint_payload):
                    yield emit(
                        _status_payload(
                            status="interrupted",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Requires user action.",
                        )
                    )
                elif not completed_payload_emitted:
                    yield emit(
                        _status_payload(
                            status="completed",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Completed",
                        )
                    )

                final_answer = collector.final_answer()
                if final_answer:
                    await _run_cleanup_task(
                        "assistant message persist",
                        _log_message_with_fresh_session(
                            request.thread_id,
                            role="assistant",
                            content=final_answer,
                            user_id=user_id,
                        ),
                    )

                    JsonLogger.log_session(
                        session_id=request.thread_id,
                        user_id=user_id,
                        event_type="turn_end",
                        metadata={"response_length": len(final_answer)},
                    )
                    JsonLogger.log_usage(
                        user_id=user_id,
                        model=DEFAULT_LLM_MODEL,
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
        except asyncio.CancelledError:
            print(
                f"[Chat] Client disconnected during stream for thread_id={request.thread_id}",
                file=sys.stderr,
                flush=True,
            )
            # Trace events will still be persisted by the finally block
            raise
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
            _append_summary_trace_events(
                request.thread_id,
                trace_events,
                reasoning_chunks,
                collector.final_answer_chunks,
            )
            if trace_events:
                await _run_cleanup_task(
                    "trace batch persist",
                    _persist_trace_events_with_fresh_session(trace_events),
                )

    return EventSourceResponse(event_generator())


@router.post("/chat/resume")
async def chat_resume_stream(
    request: ResumeRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    """Streaming endpoint to resume an interrupted graph."""
    print(
        f"[Chat] Resume Endpoint called! thread_id={request.thread_id}, action={request.action}",
        file=sys.stderr,
        flush=True,
    )

    user_id = current_user.id

    await _ensure_thread_owned_by_user(
        request.thread_id,
        user_id,
        allow_missing=False,
    )

    # Edge Case 3 & 4: Validate Thread ID and Interrupt State
    async with AsyncPostgresSaver.from_conn_string(
        settings.sync_database_uri
    ) as checkpointer:
        from langchain_core.runnables import RunnableConfig
        from typing import cast

        check_config = cast(
            RunnableConfig, {"configurable": {"thread_id": request.thread_id}}
        )
        saved_state = await checkpointer.aget_tuple(check_config)
        if not saved_state:
            raise HTTPException(status_code=404, detail="Thread not found")

        has_tasks = getattr(
            saved_state, "tasks", getattr(saved_state, "pending_sends", [])
        )
        if not has_tasks:
            try:
                builder = get_orchagent_graph()
                graph = builder.compile(checkpointer=checkpointer)
                snapshot = await graph.aget_state(check_config, subgraphs=True)
            except TypeError:
                snapshot = None

            has_tasks = bool(getattr(snapshot, "next", ()))

        if not has_tasks:
            raise HTTPException(
                status_code=400, detail="Graph is not in an interrupted state"
            )

    # 1. DB Logging
    resume_message = f"[User Action]: {request.action}"
    if request.feedback:
        resume_message += f"\nFeedback: {request.feedback}"

    await _log_message_with_fresh_session(
        request.thread_id, role="user", content=resume_message, user_id=user_id
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
        config = {
            "configurable": {"thread_id": request.thread_id},
            "recursion_limit": settings.GRAPH_RECURSION_LIMIT,
        }

        collector = _FinalResponseCollector()
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
                    event_node = _event_node_name(event)
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
                                    "node": event_node,
                                    "display_name": _display_name(event_node),
                                    "content": reasoning_chunk,
                                    "run_id": run_id,
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )

                        text_chunk = _extract_text_content(
                            getattr(chunk, "content", "")
                        )
                        for emission in collector.ingest_model_stream(event, text_chunk):
                            yield emit(
                                _text_payload_from_emission(emission),
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

                                for emission in collector.consume_head_supervisor_end(
                                    update, goto=output.goto
                                ):
                                    yield emit(
                                        _text_payload_from_emission(emission),
                                        persist=False,
                                    )

                            elif name == "finalizer":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield emit(
                                        _status_payload(
                                            status=status,
                                            thread_id=request.thread_id,
                                            node=name,
                                            message="Completed",
                                        )
                                    )
                                for emission in collector.consume_finalizer_end(update):
                                    yield emit(
                                        _text_payload_from_emission(emission),
                                        persist=False,
                                    )

                checkpoint_payload = await _build_checkpoint_payload(
                    graph, config, request.thread_id
                )

                snapshot = await graph.aget_state(config, subgraphs=True)
                state_values = (
                    snapshot.values if isinstance(snapshot.values, dict) else {}
                )
                for emission in collector.collect_state_fallback(state_values):
                    yield emit(
                        _text_payload_from_emission(emission),
                        persist=False,
                    )

                yield emit(checkpoint_payload)

                if _checkpoint_requires_user_action(checkpoint_payload):
                    yield emit(
                        _status_payload(
                            status="interrupted",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Requires user action.",
                        )
                    )
                elif not completed_payload_emitted:
                    yield emit(
                        _status_payload(
                            status="completed",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Completed",
                        )
                    )

                final_answer = collector.final_answer()
                if final_answer:
                    await _run_cleanup_task(
                        "assistant message persist",
                        _log_message_with_fresh_session(
                            request.thread_id,
                            role="assistant",
                            content=final_answer,
                            user_id=user_id,
                        ),
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
        except asyncio.CancelledError:
            print(
                f"[Chat] Client disconnected during stream for thread_id={request.thread_id}",
                file=sys.stderr,
                flush=True,
            )
            # We don't yield any more SSE events since the connection is gone,
            # but the finally block will still execute and persist trace_events.
            raise
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
            _append_summary_trace_events(
                request.thread_id,
                trace_events,
                reasoning_chunks,
                collector.final_answer_chunks,
            )
            if trace_events:
                await _run_cleanup_task(
                    "trace batch persist",
                    _persist_trace_events_with_fresh_session(trace_events),
                )

    return EventSourceResponse(event_generator())


@router.get("/thread/{thread_id}/trace")
async def get_thread_trace(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retrieve execution trace for a specific thread."""
    session = await ThreadService.get_chat_session(db, thread_id, user_id=current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    traces = await TraceService.get_thread_traces(db, thread_id)
    return {"thread_id": thread_id, "traces": traces}
