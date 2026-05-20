"""Streaming helpers shared by the chat route and downstream consumers.

Public surface:
- ``event_node_name``, ``extract_text_content`` — small generic helpers.
- ``FinalTextEmission``, ``BufferedFinalTextRun``, ``FinalResponseCollector``
  — ownership-aware collector for the user-visible ``text`` SSE event.
- ``FINAL_TEXT_STREAM_NODES``, ``INTERNAL_MESSAGE_NAMES`` — node sets that
  participate in / are filtered out of the final-response stream.
"""

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
    "FINAL_TEXT_STREAM_NODES",
    "INTERNAL_MESSAGE_NAMES",
    "BufferedFinalTextRun",
    "FinalResponseCollector",
    "FinalTextEmission",
    "event_node_name",
    "extract_text_content",
]
