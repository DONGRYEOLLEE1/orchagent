"""Standard error payload for worker tools.

Phase 4.1 of the codebase-wide refactor. Worker tools used to mix three
error-signalling styles (raise exception, return string error, return
``{"ok": False, ...}`` dict). This module pins a single shape so the
supervisor/validator and the SSE ``tool_error`` event can speak the
same vocabulary:

::

    {"ok": False, "error": {"kind": "...", "message": "...", "details": {...}}}

Tools migrate to this format incrementally — adding the helpers here is
the safe first step. Existing tools keep working until each one is
ported.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ToolErrorKind = Literal[
    "input_validation",
    "external_api",
    "timeout",
    "runtime",
    "permission",
    "not_found",
    "unknown",
]


class ToolError(BaseModel):
    """Structured error description carried inside :class:`ToolErrorPayload`."""

    kind: ToolErrorKind = Field(default="unknown")
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ToolErrorPayload(BaseModel):
    """Standard error envelope returned by a failing worker tool."""

    ok: Literal[False] = False
    error: ToolError


def make_tool_error_payload(
    *,
    kind: ToolErrorKind,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper that returns the payload as a plain ``dict`` (LangChain friendly)."""
    payload = ToolErrorPayload(
        error=ToolError(kind=kind, message=message, details=details or {}),
    )
    return payload.model_dump()


__all__ = [
    "ToolError",
    "ToolErrorKind",
    "ToolErrorPayload",
    "make_tool_error_payload",
]
