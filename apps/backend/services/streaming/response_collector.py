"""Ownership-aware collector for the user-visible ``text`` SSE stream.

This module enforces the FINAL_RESPONSE_STREAM_OWNERSHIP contract documented
in ``docs/FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT.md``: per turn, the very
first ``run_id`` whose chunks are approved becomes the sole owner of the
``text`` stream and any other run is silently buffered or dropped.

Public API:
- :data:`FINAL_TEXT_STREAM_NODES`, :data:`INTERNAL_MESSAGE_NAMES`
- :class:`FinalTextEmission`, :class:`BufferedFinalTextRun`
- :class:`FinalResponseCollector`
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from services.streaming.event_utils import event_node_name, extract_text_content

FINAL_TEXT_STREAM_NODES: frozenset[str] = frozenset(
    {"head_supervisor", "finalizer"}
)
INTERNAL_MESSAGE_NAMES: frozenset[str] = frozenset(
    {"planner", "supervisor", "reviewer", "validator"}
)


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

    node_name = event_node_name(event)
    if node_name in FINAL_TEXT_STREAM_NODES:
        run_id = event.get("run_id") or node_name
        state = structured_content_states.setdefault(run_id, {})
        if node_name == "finalizer":
            state.setdefault("next_parsed", True)
            state.setdefault("next_value", "FINISH")
        return _extract_final_supervisor_content_text(text_chunk, state)
    return ""


def _chunk_text(text: str, chunk_size: int = 24) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


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

        content = extract_text_content(getattr(message, "content", ""))
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
class FinalTextEmission:
    """A chunk that has been approved for emission to the client."""

    node: str
    content: str
    run_id: str | None = None


@dataclass
class BufferedFinalTextRun:
    """Chunks queued under a candidate ``run_id`` until ownership is decided."""

    run_id: str
    node: str
    chunks: list[str] = field(default_factory=list)


class FinalResponseCollector:
    """Decide which run owns the final-response stream and emit its chunks.

    The collector starts with no owner. The first run whose chunks are
    approved becomes ``approved_owner_run_id``; any other run is dropped.
    Head-supervisor chunks are buffered until the run is known to be a
    direct completion (``response_mode == "direct"`` or ``goto == __end__``
    or ``streaming_status == "completed"`` with ``route_history`` ending in
    ``FINISH``). Finalizer chunks are approved immediately when ingested.
    """

    def __init__(self) -> None:
        self.final_answer_chunks: list[str] = []
        self.structured_content_states: dict[str, dict[str, Any]] = {}
        self._pending_by_node: dict[str, list[BufferedFinalTextRun]] = {
            "head_supervisor": []
        }
        self.approved_owner_run_id: str | None = None
        self.approved_owner_node: str | None = None

    def ingest_model_stream(
        self,
        event: dict[str, Any],
        text_chunk: str,
    ) -> list[FinalTextEmission]:
        normalized_text_chunk = _normalize_model_text_chunk(
            event, text_chunk, self.structured_content_states
        )
        if not normalized_text_chunk:
            return []

        node_name = event_node_name(event)
        run_id = event.get("run_id") or node_name

        if node_name == "head_supervisor":
            pending_runs = self._pending_by_node.setdefault(node_name, [])
            if pending_runs and pending_runs[-1].run_id == run_id:
                pending_runs[-1].chunks.append(normalized_text_chunk)
            else:
                pending_runs.append(
                    BufferedFinalTextRun(
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
    ) -> list[FinalTextEmission]:
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

        content_str = extract_text_content(getattr(direct_messages[-1], "content", ""))
        if not content_str:
            return []

        return self._approve_chunks(
            node="head_supervisor",
            run_id=None,
            chunks=_chunk_text(content_str),
        )

    def consume_finalizer_end(self, update: dict[str, Any]) -> list[FinalTextEmission]:
        if self.final_answer_chunks:
            return []

        final_messages = update.get("messages") or []
        if not final_messages:
            return []

        content_str = extract_text_content(getattr(final_messages[-1], "content", ""))
        if not content_str:
            return []

        return self._approve_chunks(
            node="finalizer",
            run_id=None,
            chunks=_chunk_text(content_str),
        )

    def collect_state_fallback(
        self, state_values: dict[str, Any]
    ) -> list[FinalTextEmission]:
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

    def _consume_pending_run(self, node: str) -> BufferedFinalTextRun | None:
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
    ) -> list[FinalTextEmission]:
        if not chunks:
            return []

        approved_run_id = run_id or node
        if self.approved_owner_run_id is None:
            self.approved_owner_run_id = approved_run_id
            self.approved_owner_node = node
        elif self.approved_owner_run_id != approved_run_id:
            return []

        emissions: list[FinalTextEmission] = []
        for chunk in chunks:
            self.final_answer_chunks.append(chunk)
            emissions.append(
                FinalTextEmission(node=node, content=chunk, run_id=run_id)
            )
        return emissions
