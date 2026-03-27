from __future__ import annotations

import json
import re
import sys
import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
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
from services.chat_analytics_service import (
    ChatAnalyticsService,
    ChatTurnFinalizeParams,
    ChatTurnStartParams,
    LLMUsageWriteParams,
    ToolExecutionFinishParams,
    ToolExecutionStartParams,
)
from core.timezone import iso_now_kst, now_kst
from services.llm_pricing_service import LLMPricingService
from services.logging_service import LoggingService
from services.memory_agent_service import MemoryAgentService
from services.memory_service import MemoryService
from services.file_logger import JsonLogger
from services.storage_service import StorageService
from services.upload_service import UploadService
from agent_tools.runtime import (
    ToolAttachment,
    ToolRuntimeContext,
    collect_runtime_artifacts,
    reset_tool_runtime_context,
    set_tool_runtime_context,
)

router = APIRouter()
FINAL_TEXT_STREAM_NODES = {"head_supervisor", "finalizer"}
INTERNAL_MESSAGE_NAMES = {"planner", "supervisor", "reviewer", "validator"}
_BACKEND_APP_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _utc_timestamp() -> str:
    return iso_now_kst()


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
    additional_reasoning = (
        additional_kwargs.get("reasoning_summary_text")
        or additional_kwargs.get("reasoning_content")
    )
    if additional_reasoning:
        return str(additional_reasoning)

    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        collected: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type not in {"reasoning", "reasoning_summary"}:
                continue
            text_value = item.get("text") or item.get("summary")
            if isinstance(text_value, str) and text_value.strip():
                collected.append(text_value)
        if collected:
            return "".join(collected)

    return ""


def _extract_usage_payload(output: Any) -> tuple[dict[str, Any] | None, Any]:
    candidate = output
    if isinstance(candidate, dict):
        if isinstance(candidate.get("output"), list) and candidate["output"]:
            candidate = candidate["output"][-1]
        else:
            candidate = candidate.get("output") or candidate.get("response") or candidate
    elif isinstance(candidate, list) and candidate:
        candidate = candidate[-1]

    usage_metadata = getattr(candidate, "usage_metadata", None)
    if usage_metadata is None and isinstance(candidate, dict):
        usage_metadata = candidate.get("usage_metadata")

    if usage_metadata is None:
        return None, candidate

    return _serialize_value(usage_metadata), candidate


def _extract_model_name(event: dict[str, Any], message_like: Any) -> str:
    metadata = event.get("metadata") or {}
    if isinstance(metadata.get("ls_model_name"), str):
        return metadata["ls_model_name"]
    if isinstance(metadata.get("model_name"), str):
        return metadata["model_name"]

    response_metadata = getattr(message_like, "response_metadata", None)
    if isinstance(response_metadata, dict):
        model_name = response_metadata.get("model_name") or response_metadata.get("model")
        if isinstance(model_name, str) and model_name:
            return model_name

    if isinstance(message_like, dict):
        response_metadata = message_like.get("response_metadata") or {}
        model_name = response_metadata.get("model_name") or response_metadata.get("model")
        if isinstance(model_name, str) and model_name:
            return model_name

    return DEFAULT_LLM_MODEL


def _build_usage_write_params(
    *,
    event: dict[str, Any],
    user_id: str,
    thread_id: str,
    turn_id: UUID,
    trace_id: str | None,
) -> LLMUsageWriteParams | None:
    usage_metadata, message_like = _extract_usage_payload(event.get("data", {}).get("output"))
    if not usage_metadata:
        return None

    input_tokens = int(usage_metadata.get("input_tokens") or 0)
    output_tokens = int(usage_metadata.get("output_tokens") or 0)
    total_tokens = int(usage_metadata.get("total_tokens") or (input_tokens + output_tokens))
    input_details = usage_metadata.get("input_token_details") or {}
    output_details = usage_metadata.get("output_token_details") or {}
    cache_read_input_tokens = int(
        input_details.get("cache_read") or input_details.get("cached_tokens") or 0
    )
    cache_write_input_tokens = int(
        input_details.get("cache_write")
        or input_details.get("cache_creation")
        or 0
    )
    reasoning_output_tokens = int(
        output_details.get("reasoning") or output_details.get("reasoning_tokens") or 0
    )
    text_output_tokens = max(output_tokens - reasoning_output_tokens, 0)
    run_id = event.get("run_id")
    node_name = _event_node_name(event)

    return LLMUsageWriteParams(
        user_id=user_id,
        thread_id=thread_id,
        turn_id=turn_id,
        run_id=run_id,
        trace_id=trace_id,
        span_id=run_id,
        parent_span_id=None,
        node_name=node_name,
        provider="openai",
        model=_extract_model_name(event, message_like),
        request_role=node_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        cache_write_input_tokens=cache_write_input_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        text_output_tokens=text_output_tokens,
        usage_metadata=usage_metadata,
        created_at=now_kst(),
    )


def _chunk_text(text: str, chunk_size: int = 24) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _trace_event(trace_context: _TraceWriteContext, payload: dict[str, Any]):
    trace_context.seq += 1
    run_id = payload.get("run_id")
    return TraceService.build_event(
        thread_id=trace_context.thread_id,
        event_type=payload["event_type"],
        node_name=payload.get("node"),
        payload=payload,
        user_id=trace_context.user_id,
        turn_id=trace_context.turn_id,
        seq=trace_context.seq,
        run_id=run_id,
        trace_id=trace_context.trace_id,
        span_id=run_id,
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


@dataclass
class _TraceWriteContext:
    thread_id: str
    user_id: str
    turn_id: UUID | None = None
    trace_id: str | None = None
    seq: int = 0


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
        "reasoning": route_entry.get("reasoning"),
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
    thread_id: str,
    *,
    role: str,
    content: str,
    user_id: str,
    attachments: list[dict[str, str]] | None = None,
) -> Any:
    async with AsyncSessionLocal() as db:
        return await LoggingService.log_message(
            db,
            thread_id,
            role=role,
            content=content,
            user_id=user_id,
            attachments=attachments,
        )


async def _persist_trace_events_with_fresh_session(trace_events: list[Any]) -> None:
    if not trace_events:
        return

    async with AsyncSessionLocal() as db:
        await TraceService.create_events(db, trace_events)


async def _update_message_content_with_fresh_session(
    *,
    message_id: UUID,
    content: str,
) -> None:
    async with AsyncSessionLocal() as db:
        await LoggingService.update_message_content(
            db,
            message_id=message_id,
            content=content,
        )


async def _start_turn_with_fresh_session(
    *,
    thread_id: str,
    user_id: str,
    request_kind: str,
    request_message_id: UUID | None,
    started_at: datetime,
    trace_id: str,
    metadata: dict[str, Any] | None = None,
) -> Any:
    async with AsyncSessionLocal() as db:
        return await ChatAnalyticsService.start_turn(
            db,
            ChatTurnStartParams(
                thread_id=thread_id,
                user_id=user_id,
                request_kind=request_kind,
                request_message_id=request_message_id,
                started_at=started_at,
                trace_id=trace_id,
                metadata=metadata,
            ),
        )


async def _mark_turn_first_token_with_fresh_session(
    turn_id: UUID, first_token_at: datetime
) -> None:
    async with AsyncSessionLocal() as db:
        await ChatAnalyticsService.mark_first_token(db, turn_id, first_token_at)


async def _finalize_turn_with_fresh_session(
    params: ChatTurnFinalizeParams,
) -> None:
    async with AsyncSessionLocal() as db:
        await ChatAnalyticsService.finalize_turn(db, params)


async def _create_usage_event_with_fresh_session(
    params: LLMUsageWriteParams,
) -> None:
    async with AsyncSessionLocal() as db:
        snapshot = await LLMPricingService.resolve_pricing_snapshot(
            db,
            provider=params.provider,
            model=params.model,
            at=params.created_at or now_kst(),
        )
        priced_params = LLMPricingService.apply_snapshot_to_usage(params, snapshot)
        await ChatAnalyticsService.create_usage_event(db, priced_params)


async def _create_tool_execution_with_fresh_session(
    params: ToolExecutionStartParams,
) -> None:
    async with AsyncSessionLocal() as db:
        await ChatAnalyticsService.create_tool_execution(db, params)


async def _finish_tool_execution_with_fresh_session(
    params: ToolExecutionFinishParams,
) -> None:
    async with AsyncSessionLocal() as db:
        await ChatAnalyticsService.finish_tool_execution(db, params)


async def _ensure_thread_owned_by_user(
    thread_id: str, user_id: str, *, allow_missing: bool
) -> None:
    async with AsyncSessionLocal() as db:
        session = await ThreadService.get_chat_session(db, thread_id)
        if session is None and allow_missing:
            return
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=404, detail="Thread not found")


async def _persist_memory_reference_events_with_fresh_session(
    *,
    user_id: str,
    thread_id: str,
    turn_id: UUID,
    memory_ids: list[UUID],
) -> None:
    if not memory_ids:
        return

    async with AsyncSessionLocal() as db:
        await MemoryService.record_reference_events(
            db,
            user_id=user_id,
            thread_id=thread_id,
            turn_id=turn_id,
            memory_ids=memory_ids,
        )


async def _persist_memory_load_trace_with_fresh_session(
    *,
    user_id: str,
    thread_id: str,
    turn_id: UUID,
    personalization_meta: dict[str, Any],
) -> None:
    async with AsyncSessionLocal() as db:
        await TraceService.create_event(
            db,
            thread_id=thread_id,
            event_type="memory_load",
            node_name="load_memories",
            payload={
                "event_type": "memory_load",
                "memory_ids": personalization_meta.get("memory_ids", []),
                "hit_count": personalization_meta.get("hit_count", 0),
                "active_memory_count": personalization_meta.get("active_memory_count", 0),
                "source": personalization_meta.get("source"),
                "summary_used": personalization_meta.get("summary_used", False),
                "recent_used": personalization_meta.get("recent_used", False),
                "cache_hit": personalization_meta.get("cache_hit", False),
                "hit_miss": personalization_meta.get("hit_miss", "miss"),
                "context_chars": personalization_meta.get("context_chars", 0),
                "retrieval_ms": personalization_meta.get("retrieval_ms", 0),
                "thread_id": thread_id,
            },
            user_id=user_id,
            turn_id=turn_id,
        )


async def _run_memory_agent_sidecar(
    *,
    user_id: str,
    thread_id: str,
    turn_id: UUID | None,
    user_message: str,
    assistant_message: str | None,
) -> None:
    if turn_id is None:
        return

    async with AsyncSessionLocal() as db:
        saved_ids = await MemoryAgentService.process_turn(
            db,
            user_id=user_id,
            thread_id=thread_id,
            turn_id=turn_id,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        if saved_ids:
            await TraceService.create_event(
                db,
                thread_id=thread_id,
                event_type="memory_write",
                node_name="memory_agent",
                payload={
                    "event_type": "memory_write",
                    "saved_memory_ids": [str(memory_id) for memory_id in saved_ids],
                    "saved_count": len(saved_ids),
                    "user_message": user_message,
                    "assistant_message_present": bool(assistant_message),
                    "timestamp": _utc_timestamp(),
                },
                user_id=user_id,
                turn_id=turn_id,
            )


def _append_summary_trace_events(
    trace_context: _TraceWriteContext,
    trace_events: list[Any],
    reasoning_chunks: list[str],
    final_answer_chunks: list[str],
) -> None:
    if reasoning_chunks:
        trace_events.append(
            _trace_event(
                trace_context,
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
                trace_context,
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


def _attachment_prompt_block(attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return ""

    lines = ["Attached files available for this turn:"]
    for attachment in attachments:
        lines.append(
            "- "
            f"id={attachment.get('id')} "
            f"name={attachment.get('file_name')} "
            f"kind={attachment.get('kind')} "
            f"mime={attachment.get('mime_type')} "
            f"size_bytes={attachment.get('size_bytes')}"
        )
    return "\n".join(lines)


def _augment_user_message_with_attachment_context(
    message: str,
    attachments: list[dict[str, Any]],
) -> str:
    attachment_block = _attachment_prompt_block(attachments)
    if not attachment_block:
        return message

    return f"{message}\n\n{attachment_block}"


def _load_uploaded_image_base64(storage_path: str) -> str:
    data = Path(storage_path).read_bytes()
    return base64.b64encode(data).decode("utf-8")


def _resolve_storage_path(storage_path: str) -> str:
    candidate = Path(storage_path)
    if candidate.is_absolute():
        return str(candidate)

    for root in (_REPO_ROOT, _BACKEND_APP_ROOT):
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return str(resolved)

    return str((_BACKEND_APP_ROOT / candidate).resolve())


def _build_tool_runtime_attachments(
    attachments: list[dict[str, Any]],
) -> dict[str, ToolAttachment]:
    runtime_attachments: dict[str, ToolAttachment] = {}
    for index, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            continue
        storage_path = attachment.get("storage_path")
        if not isinstance(storage_path, str) or not storage_path:
            continue
        resolved_storage_path = _resolve_storage_path(storage_path)
        attachment_id = str(attachment.get("id") or f"legacy-attachment-{index + 1}")
        runtime_attachments[attachment_id] = ToolAttachment(
            id=attachment_id,
            kind=str(attachment.get("kind") or "artifact"),
            file_name=str(attachment.get("file_name") or Path(storage_path).name),
            mime_type=str(attachment.get("mime_type") or "application/octet-stream"),
            size_bytes=(
                int(attachment.get("size_bytes"))
                if isinstance(attachment.get("size_bytes"), int)
                else None
            ),
            storage_path=resolved_storage_path,
        )
    return runtime_attachments


def _build_public_attachment_payloads(
    *,
    base_url: str,
    thread_id: str,
    message_id: UUID,
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for index, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            continue
        payloads.append(
            {
                "kind": attachment.get("kind"),
                "url": f"{base_url}{ThreadService._build_attachment_url(thread_id=thread_id, message_id=message_id, attachment_index=index)}",
                "alt": attachment.get("file_name")
                or attachment.get("title")
                or (
                    f"첨부 이미지 {index + 1}"
                    if attachment.get("kind") == "image"
                    else f"첨부 파일 {index + 1}"
                ),
                "file_name": attachment.get("file_name"),
                "mime_type": attachment.get("mime_type"),
                "size_bytes": attachment.get("size_bytes"),
            }
        )
    return payloads


def _rewrite_attachment_markdown_links(
    content: str,
    public_attachments: list[dict[str, Any]],
) -> str:
    rewritten = content
    for attachment in public_attachments:
        file_name = str(attachment.get("file_name") or "").strip()
        url = str(attachment.get("url") or "").strip()
        if not file_name or not url:
            continue
        rewritten = rewritten.replace(f"({file_name})", f"({url})")
    return rewritten


def _build_visual_download_suffix(public_attachments: list[dict[str, Any]]) -> str:
    downloadables = [
        attachment
        for attachment in public_attachments
        if str(attachment.get("mime_type") or "").startswith("image/")
        or str(attachment.get("file_name") or "").lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]
    if not downloadables:
        return ""

    lines = ["", "다운로드", ""]
    for attachment in downloadables:
        label = str(attachment.get("file_name") or attachment.get("alt") or "artifact")
        url = str(attachment.get("url") or "")
        lines.append(f"- [{label}]({url})")
    return "\n".join(lines)


@router.post("/chat")
async def chat_stream(
    http_request: Request,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
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

    uploaded_files = await UploadService.resolve_uploads(
        db,
        upload_ids=request.attachment_ids,
        user_id=user_id,
    )

    # Save legacy inline images to disk and normalize them into attachment snapshots.
    image_paths: list[str] = []
    if request.images:
        image_paths = [StorageService.save_base64_image(img) for img in request.images]
    request_attachments = [
        UploadService.build_attachment_snapshot(upload) for upload in uploaded_files
    ] + [
        {
            "id": f"legacy-image-{index + 1}",
            "kind": "image",
            "storage_path": path,
            "file_name": f"image_{index + 1}.jpg",
            "mime_type": "image/jpeg",
        }
        for index, path in enumerate(image_paths)
        if path and path != "error_saving_image"
    ]
    analysis_attachments = request_attachments or await ThreadService.get_latest_user_attachments(
        db,
        thread_id=request.thread_id,
        user_id=user_id,
    )
    graph_user_message = _augment_user_message_with_attachment_context(
        request.message,
        analysis_attachments,
    )
    uploaded_image_payloads = [
        _load_uploaded_image_base64(upload.storage_path)
        for upload in uploaded_files
        if upload.kind == "image"
    ]

    # 1. DB Logging
    request_message = await _log_message_with_fresh_session(
        request.thread_id,
        role="user",
        content=request.message,
        user_id=user_id,
        attachments=request_attachments,
    )
    turn_started_at = now_kst()
    started_turn = await _start_turn_with_fresh_session(
        thread_id=request.thread_id,
        user_id=user_id,
        request_kind="chat",
        request_message_id=getattr(request_message, "id", None),
        started_at=turn_started_at,
        trace_id="",
        metadata={
            "has_images": bool(request.images or uploaded_image_payloads),
            "message_length": len(request.message),
        },
    )
    trace_context = _TraceWriteContext(
        thread_id=request.thread_id,
        user_id=user_id,
        turn_id=getattr(started_turn, "id", None),
        trace_id=getattr(started_turn, "trace_id", None)
        or str(getattr(started_turn, "id", "")),
    )

    # 2. File Logging (Session start/turn)
    JsonLogger.log_session(
        session_id=request.thread_id,
        user_id=user_id,
        event_type="turn_start",
        metadata={
            "message_length": len(request.message),
            "has_images": bool(request.images or uploaded_image_payloads),
            "image_paths": image_paths
            + [upload.storage_path for upload in uploaded_files if upload.kind == "image"],
        },
    )

    async def event_generator():
        approval_requested = requires_human_approval_for_text(request.message)

        # Construct multimodal message if images are present
        if request.images or uploaded_image_payloads:
            content: list[Any] = [{"type": "text", "text": graph_user_message}]
            for img in [*(request.images or []), *uploaded_image_payloads]:
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
                    "current_user_id": user_id,
                    "thread_id": request.thread_id,
                    "vision_routed_for_current_turn": False,
                    "attachments": analysis_attachments,
                },
            }
        else:
            inputs = {
                "messages": [("user", graph_user_message)],
                "shared_context": {
                    "force_requires_approval": approval_requested,
                    "current_user_id": user_id,
                    "thread_id": request.thread_id,
                    "vision_routed_for_current_turn": False,
                    "attachments": analysis_attachments,
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
        runtime_token = None
        collected_artifacts: list[Any] = []
        completed_payload_emitted = False
        final_checkpoint_payload: dict[str, Any] | None = None
        first_token_recorded = False
        first_token_at: datetime | None = None
        tool_call_count = 0
        final_status: str = "running"
        response_mode: str | None = None
        active_team_final: str | None = None
        active_worker_final: str | None = None
        final_status_node: str | None = None
        assistant_response_message_id: UUID | None = None
        disconnected = False
        error_message: str | None = None
        final_state_values: dict[str, Any] = {}

        async def emit(payload: dict[str, Any], *, persist: bool = True):
            nonlocal final_status, final_status_node
            nonlocal response_mode, active_team_final, active_worker_final
            nonlocal final_checkpoint_payload
            if payload.get("event_type") == "status":
                status = payload.get("status")
                if status in {"completed", "interrupted", "errored"}:
                    final_status = str(status)
                    final_status_node = payload.get("node")
                    active_team_final = payload.get("active_team") or active_team_final
                    active_worker_final = (
                        payload.get("active_worker") or active_worker_final
                    )
            elif payload.get("event_type") == "checkpoint":
                final_checkpoint_payload = payload
                response_mode = payload.get("response_mode") or response_mode
                active_team_final = payload.get("active_team") or active_team_final
                active_worker_final = payload.get("active_worker") or active_worker_final
            if persist:
                trace_events.append(_trace_event(trace_context, payload))
            return {"event": "message", "data": json.dumps(payload)}

        async def emit_text_emission(emission: _FinalTextEmission):
            nonlocal first_token_recorded, first_token_at
            if trace_context.turn_id and not first_token_recorded:
                first_token_recorded = True
                first_token_at = now_kst()
                await _mark_turn_first_token_with_fresh_session(
                    trace_context.turn_id, first_token_at
                )
            return await emit(_text_payload_from_emission(emission), persist=False)

        try:
            yield await emit(
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
                if trace_context.turn_id is not None:
                    workspace_dir, artifact_dir = StorageService.create_analysis_workspace(
                        thread_id=request.thread_id,
                        turn_id=str(trace_context.turn_id),
                    )
                    runtime_token = set_tool_runtime_context(
                        ToolRuntimeContext(
                            thread_id=request.thread_id,
                            user_id=user_id,
                            attachments=_build_tool_runtime_attachments(analysis_attachments),
                            workspace_dir=workspace_dir,
                            artifact_dir=artifact_dir,
                        )
                    )
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
                            yield await emit(
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
                            yield await emit_text_emission(emission)
                        continue

                    if kind == "on_chat_model_end" and trace_context.turn_id is not None:
                        usage_params = _build_usage_write_params(
                            event=event,
                            user_id=user_id,
                            thread_id=request.thread_id,
                            turn_id=trace_context.turn_id,
                            trace_id=trace_context.trace_id,
                        )
                        if usage_params is not None:
                            await _run_cleanup_task(
                                "usage event persist",
                                _create_usage_event_with_fresh_session(usage_params),
                            )
                        continue

                    if kind == "on_tool_start":
                        tool_call_count += 1
                        if trace_context.turn_id is not None:
                            await _run_cleanup_task(
                                "tool start persist",
                                _create_tool_execution_with_fresh_session(
                                    ToolExecutionStartParams(
                                        user_id=user_id,
                                        thread_id=request.thread_id,
                                        turn_id=trace_context.turn_id,
                                        run_id=run_id,
                                        trace_id=trace_context.trace_id,
                                        span_id=run_id,
                                        parent_span_id=None,
                                        node_name=name,
                                        tool_name=name,
                                        display_name=_display_name(name),
                                        started_at=now_kst(),
                                        input_summary=_serialize_value(data.get("input")),
                                    )
                                ),
                            )
                        yield await emit(
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
                        if trace_context.turn_id is not None:
                            await _run_cleanup_task(
                                "tool end persist",
                                _finish_tool_execution_with_fresh_session(
                                    ToolExecutionFinishParams(
                                        thread_id=request.thread_id,
                                        turn_id=trace_context.turn_id,
                                        run_id=run_id,
                                        tool_name=name,
                                        status="success",
                                        ended_at=now_kst(),
                                        output_summary=_serialize_value(data.get("output")),
                                    )
                                ),
                            )
                        yield await emit(
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
                        if trace_context.turn_id is not None:
                            await _run_cleanup_task(
                                "tool error persist",
                                _finish_tool_execution_with_fresh_session(
                                    ToolExecutionFinishParams(
                                        thread_id=request.thread_id,
                                        turn_id=trace_context.turn_id,
                                        run_id=run_id,
                                        tool_name=name,
                                        status="error",
                                        ended_at=now_kst(),
                                        error_summary=_serialize_value(data.get("error")),
                                    )
                                ),
                            )
                        yield await emit(
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
                                latest_route = route_history[-1]
                                yield await emit(_route_payload(name, latest_route))
                                route_reasoning = str(latest_route.get("reasoning") or "").strip()
                                if route_reasoning:
                                    reasoning_chunks.append(route_reasoning)
                                    yield await emit(
                                        {
                                            "event_type": "reasoning",
                                            "node": name,
                                            "display_name": _display_name(name),
                                            "content": route_reasoning,
                                            "run_id": run_id,
                                            "timestamp": _utc_timestamp(),
                                        },
                                        persist=False,
                                    )

                            if name == "head_supervisor":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield await emit(
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
                                    yield await emit_text_emission(emission)

                            elif name == "finalizer":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield await emit(
                                        _status_payload(
                                            status=status,
                                            thread_id=request.thread_id,
                                            node=name,
                                            message="Completed",
                                        )
                                    )
                                for emission in collector.consume_finalizer_end(update):
                                    yield await emit_text_emission(emission)

                checkpoint_payload = await _build_checkpoint_payload(
                    graph, config, request.thread_id
                )

                snapshot = await graph.aget_state(config, subgraphs=True)
                state_values = (
                    snapshot.values if isinstance(snapshot.values, dict) else {}
                )
                final_state_values = state_values
                for emission in collector.collect_state_fallback(state_values):
                    yield await emit_text_emission(emission)

                yield await emit(checkpoint_payload)

                if _checkpoint_requires_user_action(checkpoint_payload):
                    yield await emit(
                        _status_payload(
                            status="interrupted",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Requires user action.",
                        )
                    )
                elif not completed_payload_emitted:
                    yield await emit(
                        _status_payload(
                            status="completed",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Completed",
                        )
                    )

                final_answer = collector.final_answer()
                if runtime_token is not None:
                    collected_artifacts = collect_runtime_artifacts()
                if final_answer:
                    assistant_attachments = [
                        {
                            "kind": artifact.kind,
                            "storage_path": artifact.storage_path,
                            "file_name": artifact.file_name,
                            "mime_type": artifact.mime_type,
                            "size_bytes": artifact.size_bytes,
                            "title": artifact.title,
                        }
                        for artifact in collected_artifacts
                    ]
                    assistant_message = await _log_message_with_fresh_session(
                        request.thread_id,
                        role="assistant",
                        content=final_answer,
                        user_id=user_id,
                        attachments=assistant_attachments,
                    )
                    assistant_response_message_id = getattr(assistant_message, "id", None)
                    if assistant_response_message_id and assistant_attachments:
                        public_attachments = _build_public_attachment_payloads(
                            base_url=str(http_request.base_url).rstrip("/"),
                            thread_id=request.thread_id,
                            message_id=assistant_response_message_id,
                            attachments=assistant_attachments,
                        )
                        answer_with_links = _rewrite_attachment_markdown_links(
                            final_answer,
                            public_attachments,
                        )
                        download_suffix = _build_visual_download_suffix(public_attachments)
                        if download_suffix and download_suffix not in answer_with_links:
                            answer_with_links = f"{answer_with_links.rstrip()}\n\n{download_suffix}"
                            await _update_message_content_with_fresh_session(
                                message_id=assistant_response_message_id,
                                content=answer_with_links,
                            )
                            yield await emit(
                                {
                                    "event_type": "text",
                                    "node": "assistant",
                                    "display_name": _display_name("assistant"),
                                    "content": f"\n\n{download_suffix}",
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )
                        yield await emit(
                            {
                                "event_type": "attachments",
                                "role": "assistant",
                                "message_id": str(assistant_response_message_id),
                                "attachments": public_attachments,
                                "timestamp": _utc_timestamp(),
                            },
                            persist=False,
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
            yield await emit(
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
            disconnected = True
            # Trace events will still be persisted by the finally block
            raise
        except Exception as e:
            error_message = str(e)
            yield await emit(
                _status_payload(
                    status="errored",
                    thread_id=request.thread_id,
                    node="OrchAgent",
                    message="Execution failed.",
                )
            )
            yield await emit(
                {
                    "event_type": "error",
                    "node": "OrchAgent",
                    "message": str(e),
                    "timestamp": _utc_timestamp(),
                }
            )
        finally:
            if runtime_token is not None:
                reset_tool_runtime_context(runtime_token)
            _append_summary_trace_events(
                trace_context,
                trace_events,
                reasoning_chunks,
                collector.final_answer_chunks,
            )
            if trace_context.turn_id is not None:
                now = now_kst()
                await _run_cleanup_task(
                    "turn finalize",
                    _finalize_turn_with_fresh_session(
                        ChatTurnFinalizeParams(
                            turn_id=trace_context.turn_id,
                            status=(
                                final_status
                                if final_status in {"completed", "interrupted", "errored"}
                                else ("errored" if disconnected else "completed")
                            ),
                            response_message_id=assistant_response_message_id,
                            completed_at=(
                                now
                                if (
                                    final_status == "completed"
                                    or (
                                        final_status == "running"
                                        and not disconnected
                                    )
                                )
                                else None
                            ),
                            interrupted_at=now if final_status == "interrupted" else None,
                            errored_at=(
                                now
                                if final_status == "errored" or disconnected
                                else None
                            ),
                            final_checkpoint_id=(
                                final_checkpoint_payload.get("checkpoint_id")
                                if final_checkpoint_payload
                                else None
                            ),
                            final_status_node=final_status_node,
                            response_mode=response_mode,
                            active_team_final=active_team_final,
                            active_worker_final=active_worker_final,
                            assistant_char_count=len(collector.final_answer()),
                            tool_call_count=tool_call_count,
                            metadata={
                                "disconnected": disconnected,
                                "error_message": error_message,
                                "first_token_recorded": first_token_recorded,
                            },
                        )
                    ),
                )
            if trace_events:
                await _run_cleanup_task(
                    "trace batch persist",
                    _persist_trace_events_with_fresh_session(trace_events),
                )
            personalization_meta = (final_state_values.get("shared_context", {}) or {}).get(
                "personalization_meta", {}
            )
            personalization_memory_ids = [
                UUID(memory_id)
                for memory_id in personalization_meta.get("memory_ids", [])
                if memory_id
            ]
            if trace_context.turn_id is not None and personalization_memory_ids:
                asyncio.create_task(
                    _persist_memory_reference_events_with_fresh_session(
                        user_id=user_id,
                        thread_id=request.thread_id,
                        turn_id=trace_context.turn_id,
                        memory_ids=personalization_memory_ids,
                    )
                )
            if trace_context.turn_id is not None and personalization_meta:
                asyncio.create_task(
                    _persist_memory_load_trace_with_fresh_session(
                        user_id=user_id,
                        thread_id=request.thread_id,
                        turn_id=trace_context.turn_id,
                        personalization_meta=personalization_meta,
                    )
                )
            if trace_context.turn_id is not None and not disconnected:
                asyncio.create_task(
                    _run_memory_agent_sidecar(
                        user_id=user_id,
                        thread_id=request.thread_id,
                        turn_id=trace_context.turn_id,
                        user_message=request.message,
                        assistant_message=collector.final_answer() or None,
                    )
                )

    return EventSourceResponse(event_generator())


@router.post("/chat/resume")
async def chat_resume_stream(
    http_request: Request,
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

    request_message = await _log_message_with_fresh_session(
        request.thread_id, role="user", content=resume_message, user_id=user_id
    )
    turn_started_at = now_kst()
    started_turn = await _start_turn_with_fresh_session(
        thread_id=request.thread_id,
        user_id=user_id,
        request_kind="resume",
        request_message_id=getattr(request_message, "id", None),
        started_at=turn_started_at,
        trace_id="",
        metadata={
            "action": request.action,
            "has_feedback": bool(request.feedback),
        },
    )
    trace_context = _TraceWriteContext(
        thread_id=request.thread_id,
        user_id=user_id,
        turn_id=getattr(started_turn, "id", None),
        trace_id=getattr(started_turn, "trace_id", None)
        or str(getattr(started_turn, "id", "")),
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
            update={
                "shared_context": {
                    "current_user_id": user_id,
                    "thread_id": request.thread_id,
                }
            },
            resume={"action": request.action, "feedback": request.feedback},
        )
        config = {
            "configurable": {"thread_id": request.thread_id},
            "recursion_limit": settings.GRAPH_RECURSION_LIMIT,
        }

        collector = _FinalResponseCollector()
        reasoning_chunks: list[str] = []
        trace_events = []
        graph = None
        runtime_token = None
        collected_artifacts: list[Any] = []
        completed_payload_emitted = False
        final_checkpoint_payload: dict[str, Any] | None = None
        first_token_recorded = False
        tool_call_count = 0
        final_status: str = "running"
        response_mode: str | None = None
        active_team_final: str | None = None
        active_worker_final: str | None = None
        final_status_node: str | None = None
        assistant_response_message_id: UUID | None = None
        disconnected = False
        error_message: str | None = None
        final_state_values: dict[str, Any] = {}

        async def emit(payload: dict[str, Any], *, persist: bool = True):
            nonlocal final_status, final_status_node
            nonlocal response_mode, active_team_final, active_worker_final
            nonlocal final_checkpoint_payload
            if payload.get("event_type") == "status":
                status = payload.get("status")
                if status in {"completed", "interrupted", "errored"}:
                    final_status = str(status)
                    final_status_node = payload.get("node")
                    active_team_final = payload.get("active_team") or active_team_final
                    active_worker_final = (
                        payload.get("active_worker") or active_worker_final
                    )
            elif payload.get("event_type") == "checkpoint":
                final_checkpoint_payload = payload
                response_mode = payload.get("response_mode") or response_mode
                active_team_final = payload.get("active_team") or active_team_final
                active_worker_final = payload.get("active_worker") or active_worker_final
            if persist:
                trace_events.append(_trace_event(trace_context, payload))
            return {"event": "message", "data": json.dumps(payload)}

        async def emit_text_emission(emission: _FinalTextEmission):
            nonlocal first_token_recorded
            if trace_context.turn_id and not first_token_recorded:
                first_token_recorded = True
                await _mark_turn_first_token_with_fresh_session(
                    trace_context.turn_id, now_kst()
                )
            return await emit(_text_payload_from_emission(emission), persist=False)

        try:
            yield await emit(
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
                            yield await emit(
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
                            yield await emit_text_emission(emission)
                        continue

                    if kind == "on_chat_model_end" and trace_context.turn_id is not None:
                        usage_params = _build_usage_write_params(
                            event=event,
                            user_id=user_id,
                            thread_id=request.thread_id,
                            turn_id=trace_context.turn_id,
                            trace_id=trace_context.trace_id,
                        )
                        if usage_params is not None:
                            await _run_cleanup_task(
                                "usage event persist",
                                _create_usage_event_with_fresh_session(usage_params),
                            )
                        continue

                    if kind == "on_tool_start":
                        tool_call_count += 1
                        if trace_context.turn_id is not None:
                            await _run_cleanup_task(
                                "tool start persist",
                                _create_tool_execution_with_fresh_session(
                                    ToolExecutionStartParams(
                                        user_id=user_id,
                                        thread_id=request.thread_id,
                                        turn_id=trace_context.turn_id,
                                        run_id=run_id,
                                        trace_id=trace_context.trace_id,
                                        span_id=run_id,
                                        parent_span_id=None,
                                        node_name=name,
                                        tool_name=name,
                                        display_name=_display_name(name),
                                        started_at=now_kst(),
                                        input_summary=_serialize_value(data.get("input")),
                                    )
                                ),
                            )
                        yield await emit(
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
                        if trace_context.turn_id is not None:
                            await _run_cleanup_task(
                                "tool end persist",
                                _finish_tool_execution_with_fresh_session(
                                    ToolExecutionFinishParams(
                                        thread_id=request.thread_id,
                                        turn_id=trace_context.turn_id,
                                        run_id=run_id,
                                        tool_name=name,
                                        status="success",
                                        ended_at=now_kst(),
                                        output_summary=_serialize_value(data.get("output")),
                                    )
                                ),
                            )
                        yield await emit(
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
                        if trace_context.turn_id is not None:
                            await _run_cleanup_task(
                                "tool error persist",
                                _finish_tool_execution_with_fresh_session(
                                    ToolExecutionFinishParams(
                                        thread_id=request.thread_id,
                                        turn_id=trace_context.turn_id,
                                        run_id=run_id,
                                        tool_name=name,
                                        status="error",
                                        ended_at=now_kst(),
                                        error_summary=_serialize_value(data.get("error")),
                                    )
                                ),
                            )
                        yield await emit(
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
                                latest_route = route_history[-1]
                                yield await emit(_route_payload(name, latest_route))
                                route_reasoning = str(latest_route.get("reasoning") or "").strip()
                                if route_reasoning:
                                    reasoning_chunks.append(route_reasoning)
                                    yield await emit(
                                        {
                                            "event_type": "reasoning",
                                            "node": name,
                                            "display_name": _display_name(name),
                                            "content": route_reasoning,
                                            "run_id": run_id,
                                            "timestamp": _utc_timestamp(),
                                        },
                                        persist=False,
                                    )

                            if name == "head_supervisor":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield await emit(
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
                                    yield await emit_text_emission(emission)

                            elif name == "finalizer":
                                status = update.get("streaming_status")
                                if status:
                                    completed_payload_emitted = status == "completed"
                                    yield await emit(
                                        _status_payload(
                                            status=status,
                                            thread_id=request.thread_id,
                                            node=name,
                                            message="Completed",
                                        )
                                    )
                                for emission in collector.consume_finalizer_end(update):
                                    yield await emit_text_emission(emission)

                checkpoint_payload = await _build_checkpoint_payload(
                    graph, config, request.thread_id
                )

                snapshot = await graph.aget_state(config, subgraphs=True)
                state_values = (
                    snapshot.values if isinstance(snapshot.values, dict) else {}
                )
                final_state_values = state_values
                for emission in collector.collect_state_fallback(state_values):
                    yield await emit_text_emission(emission)

                yield await emit(checkpoint_payload)

                if _checkpoint_requires_user_action(checkpoint_payload):
                    yield await emit(
                        _status_payload(
                            status="interrupted",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Requires user action.",
                        )
                    )
                elif not completed_payload_emitted:
                    yield await emit(
                        _status_payload(
                            status="completed",
                            thread_id=request.thread_id,
                            node="OrchAgent",
                            message="Completed",
                        )
                    )

                final_answer = collector.final_answer()
                if final_answer:
                    assistant_attachments = []
                    if runtime_token is not None:
                        assistant_attachments = [
                            {
                                "kind": artifact.kind,
                                "storage_path": artifact.storage_path,
                                "file_name": artifact.file_name,
                                "mime_type": artifact.mime_type,
                                "size_bytes": artifact.size_bytes,
                                "title": artifact.title,
                            }
                            for artifact in collected_artifacts
                        ]
                    assistant_message = await _log_message_with_fresh_session(
                        request.thread_id,
                        role="assistant",
                        content=final_answer,
                        user_id=user_id,
                        attachments=assistant_attachments,
                    )
                    assistant_response_message_id = getattr(assistant_message, "id", None)
                    if assistant_response_message_id and assistant_attachments:
                        public_attachments = _build_public_attachment_payloads(
                            base_url=str(http_request.base_url).rstrip("/"),
                            thread_id=request.thread_id,
                            message_id=assistant_response_message_id,
                            attachments=assistant_attachments,
                        )
                        answer_with_links = _rewrite_attachment_markdown_links(
                            final_answer,
                            public_attachments,
                        )
                        download_suffix = _build_visual_download_suffix(public_attachments)
                        if download_suffix and download_suffix not in answer_with_links:
                            answer_with_links = f"{answer_with_links.rstrip()}\n\n{download_suffix}"
                            await _update_message_content_with_fresh_session(
                                message_id=assistant_response_message_id,
                                content=answer_with_links,
                            )
                            yield await emit(
                                {
                                    "event_type": "text",
                                    "node": "assistant",
                                    "display_name": _display_name("assistant"),
                                    "content": f"\n\n{download_suffix}",
                                    "timestamp": _utc_timestamp(),
                                },
                                persist=False,
                            )
                        yield await emit(
                            {
                                "event_type": "attachments",
                                "role": "assistant",
                                "message_id": str(assistant_response_message_id),
                                "attachments": public_attachments,
                                "timestamp": _utc_timestamp(),
                            },
                            persist=False,
                        )

                    JsonLogger.log_session(
                        session_id=request.thread_id,
                        user_id=user_id,
                        event_type="turn_end",
                        metadata={"response_length": len(final_answer)},
                    )

        except GraphInterrupt as gi:
            print(f"[Chat] Graph interrupted again: {gi}", file=sys.stderr, flush=True)
            yield await emit(
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
            disconnected = True
            # We don't yield any more SSE events since the connection is gone,
            # but the finally block will still execute and persist trace_events.
            raise
        except Exception as e:
            error_message = str(e)
            yield await emit(
                _status_payload(
                    status="errored",
                    thread_id=request.thread_id,
                    node="OrchAgent",
                    message="Execution failed.",
                )
            )
            yield await emit(
                {
                    "event_type": "error",
                    "node": "OrchAgent",
                    "message": str(e),
                    "timestamp": _utc_timestamp(),
                }
            )
        finally:
            if runtime_token is not None:
                collected_artifacts = collect_runtime_artifacts()
                reset_tool_runtime_context(runtime_token)
            _append_summary_trace_events(
                trace_context,
                trace_events,
                reasoning_chunks,
                collector.final_answer_chunks,
            )
            if trace_context.turn_id is not None:
                now = now_kst()
                await _run_cleanup_task(
                    "turn finalize",
                    _finalize_turn_with_fresh_session(
                        ChatTurnFinalizeParams(
                            turn_id=trace_context.turn_id,
                            status=(
                                final_status
                                if final_status in {"completed", "interrupted", "errored"}
                                else ("errored" if disconnected else "completed")
                            ),
                            response_message_id=assistant_response_message_id,
                            completed_at=(
                                now
                                if (
                                    final_status == "completed"
                                    or (
                                        final_status == "running"
                                        and not disconnected
                                    )
                                )
                                else None
                            ),
                            interrupted_at=now if final_status == "interrupted" else None,
                            errored_at=(
                                now
                                if final_status == "errored" or disconnected
                                else None
                            ),
                            final_checkpoint_id=(
                                final_checkpoint_payload.get("checkpoint_id")
                                if final_checkpoint_payload
                                else None
                            ),
                            final_status_node=final_status_node,
                            response_mode=response_mode,
                            active_team_final=active_team_final,
                            active_worker_final=active_worker_final,
                            assistant_char_count=len(collector.final_answer()),
                            tool_call_count=tool_call_count,
                            metadata={
                                "disconnected": disconnected,
                                "error_message": error_message,
                                "first_token_recorded": first_token_recorded,
                                "resume_action": request.action,
                            },
                        )
                    ),
                )
            if trace_events:
                await _run_cleanup_task(
                    "trace batch persist",
                    _persist_trace_events_with_fresh_session(trace_events),
                )
            personalization_meta = (final_state_values.get("shared_context", {}) or {}).get(
                "personalization_meta", {}
            )
            personalization_memory_ids = [
                UUID(memory_id)
                for memory_id in personalization_meta.get("memory_ids", [])
                if memory_id
            ]
            if trace_context.turn_id is not None and personalization_memory_ids:
                asyncio.create_task(
                    _persist_memory_reference_events_with_fresh_session(
                        user_id=user_id,
                        thread_id=request.thread_id,
                        turn_id=trace_context.turn_id,
                        memory_ids=personalization_memory_ids,
                    )
                )
            if trace_context.turn_id is not None and personalization_meta:
                asyncio.create_task(
                    _persist_memory_load_trace_with_fresh_session(
                        user_id=user_id,
                        thread_id=request.thread_id,
                        turn_id=trace_context.turn_id,
                        personalization_meta=personalization_meta,
                    )
                )
            if trace_context.turn_id is not None and not disconnected:
                resume_message_text = resume_message
                asyncio.create_task(
                    _run_memory_agent_sidecar(
                        user_id=user_id,
                        thread_id=request.thread_id,
                        turn_id=trace_context.turn_id,
                        user_message=resume_message_text,
                        assistant_message=collector.final_answer() or None,
                    )
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
