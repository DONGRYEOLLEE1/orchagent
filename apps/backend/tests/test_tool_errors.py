"""Phase 4.1 — unit tests for the shared ToolErrorPayload contract."""

from __future__ import annotations

from agent_tools.errors import (
    ToolError,
    ToolErrorPayload,
    make_tool_error_payload,
)


def test_make_tool_error_payload_shape() -> None:
    payload = make_tool_error_payload(
        kind="external_api",
        message="upstream returned 503",
        details={"status": 503, "endpoint": "/v1/search"},
    )
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "external_api"
    assert payload["error"]["message"] == "upstream returned 503"
    assert payload["error"]["details"]["status"] == 503


def test_make_tool_error_payload_defaults_details_to_empty_dict() -> None:
    payload = make_tool_error_payload(kind="timeout", message="tavily timeout")
    assert payload["error"]["details"] == {}


def test_tool_error_payload_pydantic_round_trip() -> None:
    payload = ToolErrorPayload(
        error=ToolError(kind="runtime", message="subprocess crashed"),
    )
    data = payload.model_dump()
    assert data["ok"] is False
    assert data["error"]["kind"] == "runtime"
    rebuilt = ToolErrorPayload.model_validate(data)
    assert rebuilt.error.kind == "runtime"


def test_tool_error_kind_falls_back_to_unknown() -> None:
    err = ToolError(message="not classified")
    assert err.kind == "unknown"
    assert err.details == {}
