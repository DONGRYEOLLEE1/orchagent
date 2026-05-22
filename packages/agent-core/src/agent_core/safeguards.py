"""Safety-net helpers for the LangGraph supervisor.

Phase 2.6 of the codebase-wide refactor. Plan §4.0 P3 says the supervisor
should never **override** the LLM's routing decision; it can only **block**
or **re-request** it. These helpers implement exactly that policy.

All functions are intentionally pure:

- They take the LLM's ``RouterDecision`` plus the relevant slice of state.
- They return either the same decision (allowed), or a new decision that
  forces FINISH (safety hit), or signal that a re-request is needed.
- They never call the LLM themselves — that's the caller's job.

The caller pattern looks like::

    decision = await router.decide(state, ...)
    decision, outcome = enforce_team_redirect_limit(decision, state)
    if outcome == "fallback_finish":
        log_safeguard_hit("redirect_limit", state)
    ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agent_core.config import SAFEGUARDS
from agent_core.router_schema import RouterDecision, RouterStatus


@dataclass(slots=True)
class SafeguardOutcome:
    """Result of running a chain of safeguards over an LLM router decision."""

    decision: RouterDecision
    status: RouterStatus = "accepted"
    reason_override: str | None = None

    def with_reason(self, reason: str) -> "SafeguardOutcome":
        return SafeguardOutcome(
            decision=RouterDecision(
                next=self.decision.next,
                reason=reason,
                request_review=self.decision.request_review,
                team_finished=self.decision.team_finished,
            ),
            status=self.status,
            reason_override=reason,
        )


def reject_invalid_goto(
    decision: RouterDecision,
    allowed_nodes: Iterable[str],
) -> SafeguardOutcome:
    """Force FINISH if the LLM picked a node that doesn't exist in the graph."""
    allowed = set(allowed_nodes) | {"FINISH"}
    if decision.next in allowed:
        return SafeguardOutcome(decision=decision)
    return SafeguardOutcome(
        decision=RouterDecision(
            next="FINISH",
            reason=(
                f"safeguard: LLM chose invalid node '{decision.next}'. "
                f"allowed={sorted(allowed)}."
            ),
            request_review=False,
            team_finished=True,
        ),
        status="rejected_invalid_goto",
    )


def enforce_team_redirect_limit(
    decision: RouterDecision,
    *,
    same_team_streak: int,
    limit: int = SAFEGUARDS.head_team_redirect_limit,
) -> SafeguardOutcome:
    """Force FINISH if head supervisor would loop on the same team too long."""
    if same_team_streak < limit:
        return SafeguardOutcome(decision=decision)
    return SafeguardOutcome(
        decision=RouterDecision(
            next="FINISH",
            reason=(
                f"safeguard: head supervisor redirected to the same team "
                f"{same_team_streak} times in a row (limit={limit})."
            ),
            request_review=False,
            team_finished=True,
        ),
        status="fallback_finish",
    )


def enforce_dispatch_limit(
    decision: RouterDecision,
    *,
    dispatch_count: int,
    limit: int = SAFEGUARDS.max_team_dispatches,
) -> SafeguardOutcome:
    """Force FINISH if a team supervisor has dispatched more workers than allowed."""
    if dispatch_count < limit:
        return SafeguardOutcome(decision=decision)
    return SafeguardOutcome(
        decision=RouterDecision(
            next="FINISH",
            reason=(
                f"safeguard: team dispatched workers {dispatch_count} times "
                f"this turn (limit={limit})."
            ),
            request_review=False,
            team_finished=True,
        ),
        status="fallback_finish",
    )


def fallback_decision_on_parse_failure(
    *,
    raw_text: str,
) -> RouterDecision:
    """LLM returned something the schema parser couldn't decode → FINISH."""
    snippet = (raw_text or "").strip()
    if len(snippet) > 200:
        snippet = snippet[:200] + "..."
    return RouterDecision(
        next="FINISH",
        reason=(
            "safeguard: router LLM output failed to parse as RouterDecision; "
            f"raw_snippet={snippet!r}"
        ),
        request_review=False,
        team_finished=True,
    )


def reject_coding_team_without_repo_binding(
    decision: RouterDecision,
    *,
    repo_bound: bool,
) -> SafeguardOutcome:
    """Force FINISH when the LLM picks ``coding_team`` without a bound repo.

    Coding workers require a bound repository to read/write files. When the
    router LLM selects ``coding_team`` for a thread that has no repository
    binding we cannot proceed — block and force FINISH so the head supervisor
    answers directly instead of dispatching a team that will fail.

    This is a pure P3 safeguard: it never changes a *valid* LLM decision; it
    only blocks one that violates a hard system precondition.
    """
    if decision.next != "coding_team" or repo_bound:
        return SafeguardOutcome(decision=decision)
    return SafeguardOutcome(
        decision=RouterDecision(
            next="FINISH",
            reason="safeguard: coding_team requires a bound repository.",
            request_review=False,
            team_finished=True,
        ),
        status="fallback_finish",
    )


__all__ = [
    "SafeguardOutcome",
    "enforce_dispatch_limit",
    "enforce_team_redirect_limit",
    "fallback_decision_on_parse_failure",
    "reject_coding_team_without_repo_binding",
    "reject_invalid_goto",
]
