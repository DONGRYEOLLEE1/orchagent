"""Streaming helpers shared by the chat route and downstream consumers.

Public surface:
- ``event_node_name``, ``extract_text_content`` — small generic helpers.
- ``FinalTextEmission``, ``BufferedFinalTextRun``, ``FinalResponseCollector``
  — ownership-aware collector for the user-visible ``text`` SSE event.
- ``FINAL_TEXT_STREAM_NODES``, ``INTERNAL_MESSAGE_NAMES`` — node sets that
  participate in / are filtered out of the final-response stream.
- ``display_name``, ``utc_timestamp`` — payload formatting primitives.
- ``status_payload``, ``route_payload``, ``text_payload_from_emission``,
  ``reasoning_payload``, ``tool_start_payload``, ``tool_end_payload``,
  ``tool_error_payload`` — SSE event payload builders.
- ``emit_fallback_text_stream``, ``FALLBACK_STREAM_DELAY_SECONDS`` — async
  cadence helper for review-approved / direct answers.
"""

from services.streaming.event_processor import (
    FALLBACK_STREAM_DELAY_SECONDS,
    display_name,
    emit_fallback_text_stream,
    reasoning_payload,
    route_payload,
    status_payload,
    text_payload_from_emission,
    tool_end_payload,
    tool_error_payload,
    tool_start_payload,
    utc_timestamp,
)
from services.streaming.event_utils import (
    event_node_name,
    extract_text_content,
)
from services.streaming.response_collector import (
    FINAL_TEXT_STREAM_NODES,
    INTERNAL_MESSAGE_NAMES,
    BufferedFinalTextRun,
    FinalResponseCollector,
    FinalTextEmission,
)

__all__ = [
    "FALLBACK_STREAM_DELAY_SECONDS",
    "FINAL_TEXT_STREAM_NODES",
    "INTERNAL_MESSAGE_NAMES",
    "BufferedFinalTextRun",
    "FinalResponseCollector",
    "FinalTextEmission",
    "display_name",
    "emit_fallback_text_stream",
    "event_node_name",
    "extract_text_content",
    "reasoning_payload",
    "route_payload",
    "status_payload",
    "text_payload_from_emission",
    "tool_end_payload",
    "tool_error_payload",
    "tool_start_payload",
    "utc_timestamp",
]
