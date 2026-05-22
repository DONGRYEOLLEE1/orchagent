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
- Direct-FINISH ``content`` round-trips so the head supervisor can emit
  it to the user (Phase 2.4 regression fix).
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


class _SequenceStructured:
    """Replay a sequence of (payload, raise_exc) pairs across ``ainvoke``.

    Lets us test the 1-retry policy: first call can raise/return junk and
    the second call returns a valid RouterDecision.
    """

    def __init__(self, steps: list[tuple[Any, Exception | None]]):
        self._steps = list(steps)
        self.calls = 0

    async def ainvoke(self, _messages: list[Any]) -> Any:
        index = min(self.calls, len(self._steps) - 1)
        self.calls += 1
        payload, exc = self._steps[index]
        if exc is not None:
            raise exc
        return payload


def _sequence_llm(steps: list[tuple[Any, Exception | None]]) -> _StubLLM:
    return _StubLLM(_SequenceStructured(steps))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_valid_decision_passes_through() -> None:
    decision_payload = RouterDecision(
        next="research_team",
        reason="user wants latest news",
        request_review=False,
        content="",
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
    assert decision.content == ""  # delegation must not carry direct-answer text
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
        _llm({"next": "FINISH", "reason": "trivial greeting", "content": ""}),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "accepted"
    assert decision.reason == "trivial greeting"
    assert decision.content == ""


@pytest.mark.asyncio
async def test_head_finish_with_direct_answer_content_round_trips() -> None:
    """Regression: Phase 2.4 head/team split dropped ``content`` from the
    router schema, so simple FINISH turns (e.g. "한 문장으로 자기소개
    해주세요") rendered as empty AI messages. The router must preserve
    the LLM-emitted direct answer text so the head supervisor can emit
    it via ``AIMessage(content=..., name="supervisor")``.
    """
    decision_payload = {
        "next": "FINISH",
        "reason": "사용자는 한 문장 자기소개를 요청했으며 별도 팀 위임이 필요 없습니다.",
        "request_review": False,
        "team_finished": False,
        "content": "저는 여러 전문 팀을 오케스트레이션하는 OrchAgent입니다.",
    }
    decision, status = await decide_route(
        _llm(decision_payload),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team", "coding_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "accepted"
    assert decision.content == "저는 여러 전문 팀을 오케스트레이션하는 OrchAgent입니다."


@pytest.mark.asyncio
async def test_safeguard_forced_finish_strips_direct_answer_content() -> None:
    """When a safeguard forces FINISH (invalid goto / redirect limit /
    dispatch limit / parse failure), the resulting RouterDecision must
    NOT carry direct-answer content — safeguards intercept routing for
    safety, not to author replies."""
    decision, status = await decide_route(
        _llm(
            {
                "next": "not_a_real_team",
                "reason": "oops",
                "content": "this should be discarded by the safeguard",
            }
        ),  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["research_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "rejected_invalid_goto"
    assert decision.content == ""


@pytest.mark.asyncio
async def test_parse_failure_retries_once_and_recovers() -> None:
    """Plan §4.0.5: structured-output 파싱 실패 시 1회 재요청 후 성공해야 한다."""
    recovered = RouterDecision(
        next="data_science_team",
        reason="retry recovered",
        request_review=False,
        content="",
    )
    llm = _sequence_llm(
        [
            (None, ValueError("Structured Output response does not have a parsed field")),
            (recovered, None),
        ]
    )
    decision, status = await decide_route(
        llm,  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["data_science_team"],
        layer="head",
    )
    assert decision.next == "data_science_team"
    assert decision.reason == "retry recovered"
    assert status == "accepted"
    # Ensure the underlying stub was indeed called twice (1 fail + 1 retry).
    assert llm._structured.calls == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_parse_failure_persists_across_both_attempts() -> None:
    """두 번 모두 파싱이 실패하면 safeguard FINISH로 폴백."""
    llm = _sequence_llm(
        [
            (None, ValueError("first parse fail")),
            (None, ValueError("second parse fail")),
        ]
    )
    decision, status = await decide_route(
        llm,  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["data_science_team"],
        layer="head",
    )
    assert decision.next == "FINISH"
    assert status == "parse_failed"
    assert llm._structured.calls == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_salvage_router_decision_from_raw_error_message() -> None:
    """OpenAI Responses API가 raw text content로 emit해도 error 메시지에서 JSON을 추출해 복원."""
    raw_msg = (
        "Structured Output response does not have a 'parsed' field nor a 'refusal' "
        "field. Received message: content=[{'type': 'text', 'text': "
        '\'{"next":"data_science_team","reason":"sales.csv product 분석"}\'}'
        "]"
    )
    err = ValueError(raw_msg)
    llm = _sequence_llm([(None, err), (None, err)])  # 둘 다 같은 에러
    decision, status = await decide_route(
        llm,  # type: ignore[arg-type]
        system_prompt="sys",
        messages=[],
        allowed_nodes=["data_science_team"],
        layer="head",
    )
    # Tier-3 recovery — JSON salvaged from the raw error string.
    assert decision.next == "data_science_team"
    assert "sales.csv" in decision.reason
    assert status == "accepted"
