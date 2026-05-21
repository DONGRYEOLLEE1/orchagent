"""Unit tests for ``agent_core.supervisors.llm_router.decide_route``.

Phase 2.4 — these tests pin the behaviour of the LLM-driven router
without paying for a real model call. The stubs satisfy the
``with_structured_output`` → ``ainvoke`` contract that the function
relies on, and we assert the safeguard chain behaves per plan §4.0 P3:

- Valid routing decision flows through untouched.
- Invalid ``next`` is rewritten to FINISH (rejected_invalid_goto).
- Same-team ping-pong above the limit forces FINISH (fallback_finish).
- Team dispatch limit hit forces FINISH (fallback_finish).
- LLM raises during parse → fallback FINISH (parse_failed).
- LLM returns a non-RouterDecision payload → fallback FINISH (parse_failed).
- Valid head-layer FINISH passes through cleanly.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_core.router_schema import RouterDecision
from agent_core.supervisors.llm_router import decide_route


class _StubStructured:
    """Mimics what ``llm.with_structured_output(RouterDecision)`` returns."""

    def __init__(self, payload: Any, *, raise_exc: Exception | None = None):
        self._payload = payload
        self._raise = raise_exc

    async def ainvoke(self, _messages: list[Any]) -> Any:
        if self._raise is not None:
            raise self._raise
        return self._payload


class _StubLLM:
    def __init__(self, structured: _StubStructured):
        self._structured = structured

    def with_structured_output(self, _schema):
        return self._structured


def _llm(payload: Any, *, raise_exc: Exception | None = None) -> _StubLLM:
    return _StubLLM(_StubStructured(payload, raise_exc=raise_exc))


@pytest.mark.asyncio
async def test_valid_decision_passes_through() -> None:
    decision_payload = RouterDecision(
        next="research_team",
        reason="user wants latest news",
        request_review=False,
    )
    decision, status = await decide_route(
        _llm(decision_payload),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team", "writing_team"],
        layer="head",
    )
    assert decision.next == "research_team"
    assert decision.reason == "user wants latest news"
    assert status == "accepted"


@pytest.mark.asyncio
async def test_invalid_next_is_coerced_to_finish() -> None:
    decision, status = await decide_route(
        _llm({"next": "not_a_real_team", "reason": "oops"}),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team", "writing_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "rejected_invalid_goto"
    assert "not_a_real_team" in decision.reason


@pytest.mark.asyncio
async def test_parse_failure_returns_finish_fallback() -> None:
    decision, status = await decide_route(
        _llm(payload=None, raise_exc=ValueError("bad json blob")),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "parse_failed"
    assert "safeguard" in decision.reason


@pytest.mark.asyncio
async def test_non_router_payload_is_parse_failed() -> None:
    """LLM returned something that isn't a RouterDecision / dict shape."""
    decision, status = await decide_route(
        _llm(payload="just a string"),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "parse_failed"


@pytest.mark.asyncio
async def test_head_layer_redirect_limit_forces_finish() -> None:
    decision_payload = RouterDecision(next="research_team", reason="keep digging")
    decision, status = await decide_route(
        _llm(decision_payload),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team"],
        layer="head",
        same_team_streak=10,  # well above default safeguard limit
    )
    assert decision.next == "FINISH"
    assert status == "fallback_finish"


@pytest.mark.asyncio
async def test_team_layer_dispatch_limit_forces_finish() -> None:
    decision_payload = RouterDecision(next="search_worker", reason="one more search")
    decision, status = await decide_route(
        _llm(decision_payload),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["search_worker", "web_scraper"],
        layer="team",
        dispatch_count=8,
        max_team_dispatches=8,
    )
    assert decision.next == "FINISH"
    assert status == "fallback_finish"


@pytest.mark.asyncio
async def test_head_finish_decision_is_accepted() -> None:
    decision, status = await decide_route(
        _llm({"next": "FINISH", "reason": "trivial greeting"}),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "accepted"
    assert decision.reason == "trivial greeting"
