"""Phase 2.6 — unit tests for the safety-net helpers.

These tests pin the contract documented in plan §4.0 P3: safeguards
**block** or **re-request** an LLM router decision, but never silently
rewrite a valid one.
"""

from __future__ import annotations

import pytest

from agent_core.router_schema import RouterDecision
from agent_core.safeguards import (
    SafeguardOutcome,
    enforce_dispatch_limit,
    enforce_team_redirect_limit,
    fallback_decision_on_parse_failure,
    reject_coding_team_without_repo_binding,
    reject_invalid_goto,
)


def _make_decision(next_node: str = "research_team", reason: str = "") -> RouterDecision:
    return RouterDecision(next=next_node, reason=reason, request_review=False, team_finished=False)


def test_valid_goto_passes_through_unchanged() -> None:
    decision = _make_decision("research_team")
    outcome = reject_invalid_goto(decision, ["research_team", "vision_team"])
    assert outcome.status == "accepted"
    assert outcome.decision == decision


def test_invalid_goto_forces_finish_with_reason() -> None:
    decision = _make_decision("non_existent_node")
    outcome = reject_invalid_goto(decision, ["research_team", "vision_team"])
    assert outcome.status == "rejected_invalid_goto"
    assert outcome.decision.next == "FINISH"
    assert "non_existent_node" in outcome.decision.reason
    assert "research_team" in outcome.decision.reason
    assert "vision_team" in outcome.decision.reason


def test_finish_is_always_allowed() -> None:
    decision = _make_decision("FINISH")
    outcome = reject_invalid_goto(decision, ["research_team"])
    assert outcome.status == "accepted"
    assert outcome.decision.next == "FINISH"


def test_team_redirect_under_limit_passes_through() -> None:
    decision = _make_decision("research_team")
    outcome = enforce_team_redirect_limit(decision, same_team_streak=1, limit=2)
    assert outcome.status == "accepted"
    assert outcome.decision == decision


def test_team_redirect_at_limit_forces_finish() -> None:
    decision = _make_decision("research_team")
    outcome = enforce_team_redirect_limit(decision, same_team_streak=2, limit=2)
    assert outcome.status == "fallback_finish"
    assert outcome.decision.next == "FINISH"
    assert "2" in outcome.decision.reason


def test_dispatch_under_limit_passes_through() -> None:
    decision = _make_decision("web_scraper")
    outcome = enforce_dispatch_limit(decision, dispatch_count=3, limit=8)
    assert outcome.status == "accepted"
    assert outcome.decision == decision


def test_dispatch_at_limit_forces_finish() -> None:
    decision = _make_decision("web_scraper")
    outcome = enforce_dispatch_limit(decision, dispatch_count=8, limit=8)
    assert outcome.status == "fallback_finish"
    assert outcome.decision.next == "FINISH"


def test_parse_failure_fallback_includes_snippet() -> None:
    raw = "this is not json {next: 'finalizer'"
    decision = fallback_decision_on_parse_failure(raw_text=raw)
    assert decision.next == "FINISH"
    assert "safeguard" in decision.reason
    assert raw[:50] in decision.reason
    assert decision.team_finished is True


def test_parse_failure_truncates_long_snippets() -> None:
    raw = "x" * 500
    decision = fallback_decision_on_parse_failure(raw_text=raw)
    assert decision.next == "FINISH"
    # 200-char snippet + ellipsis marker
    assert "..." in decision.reason
    assert len(decision.reason) < 350


def test_safeguard_outcome_with_reason_preserves_next_and_status() -> None:
    base = SafeguardOutcome(
        decision=_make_decision("FINISH", reason="orig"),
        status="fallback_finish",
    )
    overridden = base.with_reason("new reason text")
    assert overridden.decision.next == "FINISH"
    assert overridden.status == "fallback_finish"
    assert overridden.decision.reason == "new reason text"


def test_router_decision_default_values_are_safe() -> None:
    decision = RouterDecision(next="finalizer")
    assert decision.reason == ""
    assert decision.request_review is False
    assert decision.team_finished is False


def test_coding_team_with_repo_binding_passes_through() -> None:
    decision = _make_decision("coding_team")
    outcome = reject_coding_team_without_repo_binding(decision, repo_bound=True)
    assert outcome.status == "accepted"
    assert outcome.decision == decision


def test_coding_team_without_repo_binding_forces_finish() -> None:
    decision = _make_decision("coding_team")
    outcome = reject_coding_team_without_repo_binding(decision, repo_bound=False)
    assert outcome.status == "fallback_finish"
    assert outcome.decision.next == "FINISH"
    assert "safeguard" in outcome.decision.reason
    assert "coding_team" in outcome.decision.reason


def test_non_coding_team_decision_unaffected_by_repo_binding_safeguard() -> None:
    """다른 팀 결정은 repo_binding 여부와 무관 — safeguard 사이드이펙트 없음."""
    decision = _make_decision("research_team")
    outcome = reject_coding_team_without_repo_binding(decision, repo_bound=False)
    assert outcome.status == "accepted"
    assert outcome.decision == decision
