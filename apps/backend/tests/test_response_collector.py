"""Unit tests for services.streaming.response_collector.

Pins the FINAL_RESPONSE_STREAM_OWNERSHIP contract in
docs/FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT.md: only the first ``run_id``
whose chunks are approved owns the ``text`` stream for a given turn.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from services.streaming.response_collector import (
    FINAL_TEXT_STREAM_NODES,
    INTERNAL_MESSAGE_NAMES,
    BufferedFinalTextRun,
    FinalResponseCollector,
    FinalTextEmission,
)


def _model_stream_event(
    *, node: str, run_id: str | None = "run-a", content_finish: bool = True
) -> dict[str, Any]:
    """Build a stream event that mimics what ingest_model_stream receives.

    The finalizer path sets ``next_value`` automatically; the head_supervisor
    path needs an explicit ``"next": "FINISH"`` so the JSON-shaped content
    parser unwraps it to a plain string.
    """
    return {
        "metadata": {"langgraph_node": node},
        "run_id": run_id,
        "name": node,
    }


def _structured_chunk(text: str, *, finish: bool = True) -> str:
    next_value = "FINISH" if finish else "PLANNER"
    return f'{{"next": "{next_value}", "content": "{text}"}}'


def test_constants_match_known_node_sets() -> None:
    assert FINAL_TEXT_STREAM_NODES == frozenset({"head_supervisor", "finalizer"})
    assert "planner" in INTERNAL_MESSAGE_NAMES
    assert "supervisor" in INTERNAL_MESSAGE_NAMES
    assert "reviewer" in INTERNAL_MESSAGE_NAMES
    assert "validator" in INTERNAL_MESSAGE_NAMES


def test_finalizer_first_emission_takes_ownership() -> None:
    collector = FinalResponseCollector()
    event = _model_stream_event(node="finalizer", run_id="finalizer-run-1")
    emissions = collector.ingest_model_stream(event, _structured_chunk("hello"))

    assert collector.approved_owner_run_id == "finalizer-run-1"
    assert collector.approved_owner_node == "finalizer"
    assert collector.final_answer() == "hello"
    assert all(isinstance(e, FinalTextEmission) for e in emissions)


def test_head_supervisor_chunks_are_buffered_until_direct_completion() -> None:
    collector = FinalResponseCollector()
    event = _model_stream_event(node="head_supervisor", run_id="head-run-1")
    chunk = _structured_chunk("direct answer body")

    # Ingest does not emit yet — head_supervisor needs end-of-run resolution
    assert collector.ingest_model_stream(event, chunk) == []
    assert collector.approved_owner_run_id is None
    assert collector.final_answer() == ""
    pending = collector._pending_by_node["head_supervisor"]
    assert pending and pending[0].run_id == "head-run-1"

    # End event: direct completion → buffered chunks get approved
    emissions = collector.consume_head_supervisor_end(
        {"response_mode": "direct"},
        goto="__end__",
    )

    assert emissions, "direct completion must emit the buffered chunks"
    assert collector.approved_owner_run_id == "head-run-1"
    assert collector.final_answer() == "direct answer body"


def test_head_supervisor_chunks_dropped_when_not_direct_completion() -> None:
    collector = FinalResponseCollector()
    event = _model_stream_event(node="head_supervisor", run_id="head-run-1")
    collector.ingest_model_stream(event, _structured_chunk("transient text"))

    emissions = collector.consume_head_supervisor_end(
        {"response_mode": "team", "streaming_status": "running"},
        goto="research_team",
    )

    assert emissions == []
    assert collector.approved_owner_run_id is None
    assert collector.final_answer() == ""


def test_second_run_id_is_ignored_after_owner_locks_in() -> None:
    """The ownership gate must hold for the entire turn."""
    collector = FinalResponseCollector()

    first_event = _model_stream_event(node="finalizer", run_id="finalizer-run-1")
    collector.ingest_model_stream(first_event, _structured_chunk("first emission"))
    assert collector.approved_owner_run_id == "finalizer-run-1"

    second_event = _model_stream_event(node="finalizer", run_id="finalizer-run-2")
    emissions = collector.ingest_model_stream(
        second_event, _structured_chunk("second emission")
    )

    assert emissions == [], "non-owner run_id must be dropped"
    assert collector.final_answer() == "first emission"
    assert collector.approved_owner_run_id == "finalizer-run-1"


def test_consume_finalizer_end_uses_state_messages_when_no_stream_chunks() -> None:
    collector = FinalResponseCollector()

    final_message = AIMessage(content="fallback from finalizer state")
    emissions = collector.consume_finalizer_end({"messages": [final_message]})

    assert emissions
    assert collector.final_answer() == "fallback from finalizer state"
    assert collector.approved_owner_node == "finalizer"


def test_consume_finalizer_end_is_noop_when_already_emitted() -> None:
    collector = FinalResponseCollector()

    primary_event = _model_stream_event(node="finalizer", run_id="finalizer-run-1")
    collector.ingest_model_stream(primary_event, _structured_chunk("already approved"))
    assert collector.final_answer() == "already approved"

    extra = collector.consume_finalizer_end(
        {"messages": [AIMessage(content="should not be emitted")]}
    )

    assert extra == []
    assert collector.final_answer() == "already approved"


def test_collect_state_fallback_skips_internal_messages() -> None:
    collector = FinalResponseCollector()

    state = {
        "messages": [
            AIMessage(content="**[Planner] internal**", name="planner"),
            AIMessage(content="FINISH", name="supervisor"),
            AIMessage(content="real user-visible answer", name="finalizer"),
        ]
    }
    emissions = collector.collect_state_fallback(state)

    assert emissions
    assert collector.final_answer() == "real user-visible answer"
    assert collector.approved_owner_node == "assistant"


def test_collect_state_fallback_returns_empty_when_already_emitted() -> None:
    collector = FinalResponseCollector()
    event = _model_stream_event(node="finalizer", run_id="finalizer-run-1")
    collector.ingest_model_stream(event, _structured_chunk("primary"))
    assert collector.final_answer() == "primary"

    extra = collector.collect_state_fallback(
        {"messages": [AIMessage(content="should-not-appear", name="finalizer")]}
    )
    assert extra == []


def test_buffered_run_dataclass_appends_chunks_in_order() -> None:
    collector = FinalResponseCollector()
    event = _model_stream_event(node="head_supervisor", run_id="head-run-1")

    collector.ingest_model_stream(event, _structured_chunk("hello "))
    collector.ingest_model_stream(event, _structured_chunk("world"))

    pending: list[BufferedFinalTextRun] = collector._pending_by_node["head_supervisor"]
    assert len(pending) == 1
    assert pending[0].run_id == "head-run-1"
    # Each ingest passes through the structured-content parser, so we expect the
    # decoded payloads (not the raw JSON) to be queued.
    assert "hello " in pending[0].chunks[0]
