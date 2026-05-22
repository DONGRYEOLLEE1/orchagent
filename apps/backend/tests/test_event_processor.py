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
    emit_fallback_text_stream,
    reasoning_payload,
    route_payload,
    status_payload,
    text_payload_from_emission,
    tool_end_payload,
    tool_error_payload,
    tool_start_payload,
)
from services.streaming.response_collector import FinalTextEmission


@pytest.mark.parametrize(
    "kwargs,expected_display_name,expected_team,expected_worker",
    [
        # Worker present → display picks the most-specific worker name. Also
        # implicitly asserts utc_timestamp() returns an ISO string with "T".
        (
            {
                "status": "running",
                "thread_id": "thread-1",
                "node": "head_supervisor",
                "message": "Working",
                "active_team": "research_team",
                "active_worker": "web_scraper",
            },
            "Web Scraper",
            "research_team",
            "web_scraper",
        ),
        # No team/worker → falls back to node display name.
        (
            {
                "status": "completed",
                "thread_id": "t",
                "node": "finalizer",
                "message": "done",
            },
            "Finalizer",
            None,
            None,
        ),
    ],
)
def test_status_payload_shape(kwargs, expected_display_name, expected_team, expected_worker) -> None:
    payload = status_payload(**kwargs)
    assert payload["event_type"] == "status"
    assert payload["status"] == kwargs["status"]
    assert payload["display_name"] == expected_display_name
    assert payload["active_team"] == expected_team
    assert payload["active_worker"] == expected_worker
    assert "timestamp" in payload and "T" in payload["timestamp"]


@pytest.mark.parametrize(
    "route_entry,expected_target,expected_display,expected_reasoning",
    [
        (
            {
                "next": "research_team",
                "team": "research_team",
                "worker": None,
                "layer": "head",
                "node": "head_supervisor",
                "status": "pending",
                "reasoning": "tavily search needed",
            },
            "research_team",
            "Research Team",
            "tavily search needed",
        ),
        ({}, None, None, None),
    ],
)
def test_route_payload_shape(route_entry, expected_target, expected_display, expected_reasoning) -> None:
    payload = route_payload("head_supervisor", route_entry)
    assert payload["event_type"] == "route"
    assert payload["target"] == expected_target
    assert payload["display_name"] == expected_display
    assert payload["reasoning"] == expected_reasoning


def test_text_and_reasoning_payload_shapes() -> None:
    """text/reasoning payloads share the (node, display_name, content, run_id)
    contract — pin both in one place."""
    text = text_payload_from_emission(FinalTextEmission(node="finalizer", content="hello", run_id="r-1"))
    assert text["event_type"] == "text"
    assert text["node"] == "finalizer"
    assert text["display_name"] == "Finalizer"
    assert text["content"] == "hello"

    reasoning = reasoning_payload(
        node="head_supervisor", content="요청은 간단한 질의.", run_id="r-1"
    )
    assert reasoning["event_type"] == "reasoning"
    assert reasoning["display_name"] == "Head Supervisor"
    assert reasoning["content"] == "요청은 간단한 질의."
    assert reasoning["run_id"] == "r-1"


def test_tool_payload_shapes() -> None:
    """Tool start/end/error payloads must each populate the correct event_type and
    payload field. The 3 builders are bundled because they exist solely to mirror the
    SSE contract; the taxonomy invariant lives in
    test_payload_builders_use_consistent_event_type_set."""
    start = tool_start_payload(
        name="scrape_webpages",
        input_summary={"url": "https://example.com"},
        run_id="r-1",
    )
    assert start["event_type"] == "tool_start"
    assert start["tool_name"] == "scrape_webpages"
    assert start["display_name"] == "Scrape Webpages"
    assert start["input"] == {"url": "https://example.com"}

    end = tool_end_payload(name="scrape_webpages", output_summary="(truncated)", run_id="r-1")
    assert end["event_type"] == "tool_end"
    assert end["output"] == "(truncated)"

    err = tool_error_payload(name="scrape_webpages", error_summary="timeout", run_id="r-1")
    assert err["event_type"] == "tool_error"
    assert err["error"] == "timeout"


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


@pytest.mark.parametrize(
    "emissions,expected_contents",
    [
        (
            [
                FinalTextEmission(node="finalizer", content="a", run_id="r"),
                FinalTextEmission(node="finalizer", content="b", run_id="r"),
                FinalTextEmission(node="finalizer", content="c", run_id="r"),
            ],
            ["a", "b", "c"],
        ),
        ([], []),
    ],
)
def test_emit_fallback_text_stream(emissions, expected_contents) -> None:
    async def fake_emit(emission: FinalTextEmission) -> dict[str, object]:
        return {"content": emission.content}

    async def drain() -> list[dict[str, object]]:
        return [
            payload
            async for payload in emit_fallback_text_stream(emissions, fake_emit, delay=0)
        ]

    result = asyncio.run(drain())
    assert [item["content"] for item in result] == expected_contents
    # Implicit pin on the FALLBACK_STREAM_DELAY_SECONDS constant range.
    assert 0 < FALLBACK_STREAM_DELAY_SECONDS < 0.5
