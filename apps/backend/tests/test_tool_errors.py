"""Phase 4.1 — unit tests for the shared ToolErrorPayload contract."""

from __future__ import annotations

from agent_tools.errors import (
    ToolError,
    ToolErrorPayload,
    make_tool_error_payload,
)


def test_make_tool_error_payload_shape_and_defaults() -> None:
    """Helper must produce ``ok=False`` envelopes, with empty details by default."""
    payload = make_tool_error_payload(
        kind="external_api",
        message="upstream returned 503",
        details={"status": 503, "endpoint": "/v1/search"},
    )
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "external_api"
    assert payload["error"]["details"]["status"] == 503

    default = make_tool_error_payload(kind="timeout", message="tavily timeout")
    assert default["error"]["details"] == {}


def test_tool_error_payload_pydantic_round_trip_and_unknown_kind() -> None:
    """Pydantic round-trip preserves shape; missing kind defaults to 'unknown'."""
    payload = ToolErrorPayload(error=ToolError(kind="runtime", message="subprocess crashed"))
    data = payload.model_dump()
    rebuilt = ToolErrorPayload.model_validate(data)
    assert rebuilt.error.kind == "runtime"

    err = ToolError(message="not classified")
    assert err.kind == "unknown"
    assert err.details == {}
