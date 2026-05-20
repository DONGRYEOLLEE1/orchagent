"""Generic helpers shared by chat-route streaming and the response collector.

Kept intentionally small. Anything specific to the final-response ownership
gate lives in :mod:`services.streaming.response_collector`.
"""

from __future__ import annotations

from typing import Any


def event_node_name(event: dict[str, Any]) -> str:
    """Return the LangGraph node name attached to a stream event.

    Falls back to the event ``name`` then ``"unknown"`` so callers never get
    an empty string for routing/ownership decisions.
    """
    metadata = event.get("metadata") or {}
    return metadata.get("langgraph_node") or event.get("name", "unknown")


def extract_text_content(content: Any) -> str:
    """Flatten a LangChain message content into a plain string.

    Handles strings, lists of (str | {type:text} | {content:...}) parts, and
    falls back to ``str(content)`` for anything unrecognised so we never
    silently drop user-visible text.
    """
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
                    parts.append(extract_text_content(item["content"]))
        return "".join(parts)
    return str(content)
