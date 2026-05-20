"""Unit tests for services.streaming.event_processor.

Phase 1.2: pins the SSE payload shapes that both chat_stream and
chat_resume_stream now share. Any drift in event_type, field names, or
display_name handling is caught here before it reaches the frontend SSE
parser.
"""

from __future__ import annotations

import asyncio

import pytest

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
from services.streaming.response_collector import FinalTextEmission


def test_display_name_handles_known_special_cases() -> None:
    assert display_name(None) is None
    assert display_name("") is None
    assert display_name("head_supervisor") == "Head Supervisor"
    assert display_name("supervisor") == "Team Supervisor"
    assert display_name("FINISH") == "Completed"
    assert display_name("research_team") == "Research Team"
    assert display_name("vision_team") == "Vision Team"
    assert display_name("web_scraper") == "Web Scraper"


def test_utc_timestamp_returns_iso_string() -> None:
    ts = utc_timestamp()
    assert isinstance(ts, str)
    # KST iso strings include 'T' and a timezone offset (or Z); they should at
    # least contain the date separator so the SSE consumer can parse them.
    assert "T" in ts


def test_status_payload_includes_required_fields() -> None:
    payload = status_payload(
        status="running",
        thread_id="thread-1",
        node="head_supervisor",
        message="Working",
        active_team="research_team",
        active_worker="web_scraper",
    )

    assert payload["event_type"] == "status"
    assert payload["status"] == "running"
    assert payload["thread_id"] == "thread-1"
    assert payload["node"] == "head_supervisor"
    assert payload["active_team"] == "research_team"
    assert payload["active_worker"] == "web_scraper"
    # display_name should pick the worker first (most specific)
    assert payload["display_name"] == "Web Scraper"
    assert payload["message"] == "Working"
    assert "timestamp" in payload


def test_route_payload_resolves_display_target() -> None:
    route_entry = {
        "next": "research_team",
        "team": "research_team",
        "worker": None,
        "layer": "head",
        "node": "head_supervisor",
        "status": "pending",
        "reasoning": "tavily search needed",
    }
    payload = route_payload("head_supervisor", route_entry)

    assert payload["event_type"] == "route"
    assert payload["target"] == "research_team"
    assert payload["display_name"] == "Research Team"
    assert payload["reasoning"] == "tavily search needed"


def test_text_payload_from_emission_round_trip() -> None:
    emission = FinalTextEmission(node="finalizer", content="hello", run_id="r-1")
    payload = text_payload_from_emission(emission)

    assert payload["event_type"] == "text"
    assert payload["node"] == "finalizer"
    assert payload["display_name"] == "Finalizer"
    assert payload["content"] == "hello"
    assert payload["run_id"] == "r-1"


def test_reasoning_payload_shape() -> None:
    payload = reasoning_payload(
        node="head_supervisor", content="요청은 간단한 질의.", run_id="r-1"
    )
    assert payload["event_type"] == "reasoning"
    assert payload["node"] == "head_supervisor"
    assert payload["display_name"] == "Head Supervisor"
    assert payload["content"] == "요청은 간단한 질의."
    assert payload["run_id"] == "r-1"


def test_tool_start_payload_shape() -> None:
    payload = tool_start_payload(
        name="scrape_webpages",
        input_summary={"url": "https://example.com"},
        run_id="r-1",
    )
    assert payload["event_type"] == "tool_start"
    assert payload["node"] == "scrape_webpages"
    assert payload["tool_name"] == "scrape_webpages"
    assert payload["display_name"] == "Scrape Webpages"
    assert payload["input"] == {"url": "https://example.com"}
    assert payload["run_id"] == "r-1"


def test_tool_end_payload_shape() -> None:
    payload = tool_end_payload(
        name="scrape_webpages",
        output_summary="(truncated)",
        run_id="r-1",
    )
    assert payload["event_type"] == "tool_end"
    assert payload["output"] == "(truncated)"
    assert payload["node"] == "scrape_webpages"


def test_tool_error_payload_shape() -> None:
    payload = tool_error_payload(
        name="scrape_webpages",
        error_summary="timeout",
        run_id="r-1",
    )
    assert payload["event_type"] == "tool_error"
    assert payload["error"] == "timeout"


def test_payload_builders_use_consistent_event_type_set() -> None:
    """Pin the exact event_type taxonomy used by the SSE contract."""
    event_types = {
        status_payload(
            status="running", thread_id="t", node="x", message=""
        )["event_type"],
        route_payload("x", {"next": "y"})["event_type"],
        text_payload_from_emission(
            FinalTextEmission(node="x", content="", run_id="r")
        )["event_type"],
        reasoning_payload(node="x", content="", run_id="r")["event_type"],
        tool_start_payload(name="x", input_summary=None, run_id="r")["event_type"],
        tool_end_payload(name="x", output_summary=None, run_id="r")["event_type"],
        tool_error_payload(name="x", error_summary=None, run_id="r")["event_type"],
    }
    assert event_types == {
        "status",
        "route",
        "text",
        "reasoning",
        "tool_start",
        "tool_end",
        "tool_error",
    }


def test_fallback_delay_constant_within_sane_range() -> None:
    assert 0 < FALLBACK_STREAM_DELAY_SECONDS < 0.5


def test_emit_fallback_text_stream_yields_in_order_with_delays() -> None:
    emissions = [
        FinalTextEmission(node="finalizer", content="a", run_id="r"),
        FinalTextEmission(node="finalizer", content="b", run_id="r"),
        FinalTextEmission(node="finalizer", content="c", run_id="r"),
    ]

    async def fake_emit(emission: FinalTextEmission) -> dict[str, object]:
        return {"content": emission.content}

    async def drain() -> list[dict[str, object]]:
        return [
            payload
            async for payload in emit_fallback_text_stream(emissions, fake_emit, delay=0)
        ]

    result = asyncio.run(drain())
    assert [item["content"] for item in result] == ["a", "b", "c"]


def test_emit_fallback_text_stream_handles_empty_iterable() -> None:
    async def fake_emit(emission: FinalTextEmission) -> dict[str, object]:
        return {"content": emission.content}

    async def drain() -> list[object]:
        return [
            payload
            async for payload in emit_fallback_text_stream([], fake_emit, delay=0)
        ]

    assert asyncio.run(drain()) == []


def test_status_payload_falls_back_to_node_when_team_and_worker_missing() -> None:
    payload = status_payload(
        status="completed",
        thread_id="t",
        node="finalizer",
        message="done",
    )
    assert payload["display_name"] == "Finalizer"
    assert payload["active_team"] is None
    assert payload["active_worker"] is None


def test_route_payload_handles_missing_optional_fields() -> None:
    payload = route_payload("head_supervisor", {})
    assert payload["event_type"] == "route"
    assert payload["target"] is None
    assert payload["display_name"] is None
    assert payload["reasoning"] is None
