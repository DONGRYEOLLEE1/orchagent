"""SSE payload builders + small streaming helpers shared by the chat route.

Phase 1.2 of the codebase-wide refactor pulls the dict-literal SSE payloads
out of ``api/routes/chat.py`` so both ``chat_stream`` and ``chat_resume_stream``
emit byte-identical payloads (one source of truth) and so each payload
shape can be unit-tested in isolation.

Public surface:
- :func:`display_name`, :func:`utc_timestamp` — formatting primitives
- :func:`status_payload`, :func:`route_payload`, :func:`text_payload_from_emission`
- :func:`reasoning_payload`, :func:`tool_start_payload`, :func:`tool_end_payload`,
  :func:`tool_error_payload`
- :func:`emit_fallback_text_stream` — async cadence generator for
  review-approved / direct answers
- :data:`FALLBACK_STREAM_DELAY_SECONDS`
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable

from core.timezone import iso_now_kst

from services.streaming.response_collector import FinalTextEmission


def utc_timestamp() -> str:
    return iso_now_kst()


def display_name(name: str | None) -> str | None:
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


def status_payload(
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
        "display_name": display_name(active_worker or active_team or node),
        "active_team": active_team,
        "active_worker": active_worker,
        "message": message,
        "timestamp": utc_timestamp(),
    }


def route_payload(node: str, route_entry: dict[str, Any]) -> dict[str, Any]:
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
        "reasoning": route_entry.get("reasoning"),
        "display_name": display_name(display_target),
        "timestamp": utc_timestamp(),
    }


def text_payload_from_emission(emission: FinalTextEmission) -> dict[str, Any]:
    return {
        "event_type": "text",
        "node": emission.node,
        "display_name": display_name(emission.node),
        "content": emission.content,
        "run_id": emission.run_id,
        "timestamp": utc_timestamp(),
    }


def reasoning_payload(
    *,
    node: str,
    content: str,
    run_id: str | None,
) -> dict[str, Any]:
    return {
        "event_type": "reasoning",
        "node": node,
        "display_name": display_name(node),
        "content": content,
        "run_id": run_id,
        "timestamp": utc_timestamp(),
    }


def tool_start_payload(
    *,
    name: str,
    input_summary: Any,
    run_id: str | None,
) -> dict[str, Any]:
    return {
        "event_type": "tool_start",
        "node": name,
        "tool_name": name,
        "display_name": display_name(name),
        "input": input_summary,
        "run_id": run_id,
        "timestamp": utc_timestamp(),
    }


def tool_end_payload(
    *,
    name: str,
    output_summary: Any,
    run_id: str | None,
) -> dict[str, Any]:
    return {
        "event_type": "tool_end",
        "node": name,
        "tool_name": name,
        "display_name": display_name(name),
        "output": output_summary,
        "run_id": run_id,
        "timestamp": utc_timestamp(),
    }


def tool_error_payload(
    *,
    name: str,
    error_summary: Any,
    run_id: str | None,
) -> dict[str, Any]:
    return {
        "event_type": "tool_error",
        "node": name,
        "tool_name": name,
        "display_name": display_name(name),
        "error": error_summary,
        "run_id": run_id,
        "timestamp": utc_timestamp(),
    }


# Cadence between fallback text chunks so review-approved / direct answers render
# as a token-like stream in the UI instead of flushing in a single frame.
FALLBACK_STREAM_DELAY_SECONDS = 0.02


async def emit_fallback_text_stream(
    emissions: Iterable[FinalTextEmission],
    emit_text_emission: Callable[[FinalTextEmission], Awaitable[Any]],
    delay: float = FALLBACK_STREAM_DELAY_SECONDS,
) -> AsyncIterator[Any]:
    """Yield text emissions one chunk at a time with a small inter-chunk delay."""
    first = True
    for emission in emissions:
        if not first:
            await asyncio.sleep(delay)
        first = False
        payload = await emit_text_emission(emission)
        yield payload
