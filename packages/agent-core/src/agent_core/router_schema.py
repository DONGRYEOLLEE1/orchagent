"""Structured-output schema for the LangGraph supervisor LLM router.

Phase 2.5 of the codebase-wide refactor. Plan §4.0 P1 says all routing
decisions are made by an LLM. To keep that decision machine-parsable
(and to allow `with_structured_output` enforcement at the LangChain
layer), the LLM is asked to emit a ``RouterDecision`` JSON object.

Field semantics:

- ``next``: the node name the LLM wants the graph to transition to.
  ``"FINISH"`` ends the turn at the head level. A team supervisor uses
  worker node names like ``"web_scraper"`` or ``"codebase_explorer"``.
- ``reason``: short human-readable explanation, exposed to the UI via
  the ``route`` SSE event (plan §4.0 P4).
- ``request_review``: ``True`` if the supervisor wants to interrupt for
  HITL approval before continuing. Replaces the rule-based
  ``_should_force_approval`` heuristic.
- ``team_finished``: team supervisor asserts the team has nothing more
  to do this turn; head supervisor uses this to decide between another
  team dispatch and a finalizer call.
- ``content``: optional user-facing answer text. Populated only when the
  head supervisor decides ``next == "FINISH"`` for a simple turn it can
  answer itself (greetings, identity, general common-sense). Empty
  string when the LLM is delegating to a team — downstream workers /
  finalizer own the visible response in that case. Without this field,
  direct-FINISH turns would emit an empty AI message (regression seen
  after the head/team split in Phase 2.4).

This schema lives in agent_core so that both supervisor.py (today's
rule-based logic) and the upcoming ``LLMRouter`` class can share it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouterDecision(BaseModel):
    """LLM router output. Validated via ``with_structured_output``."""

    next: str = Field(
        description=(
            "Target node name to transition to, or 'FINISH' to end the turn."
        )
    )
    reason: str = Field(
        default="",
        description="Short justification. Shown to the user via the route SSE event.",
    )
    request_review: bool = Field(
        default=False,
        description=(
            "Set True when the supervisor wants to pause for human approval "
            "before continuing (replaces _should_force_approval heuristic)."
        ),
    )
    team_finished: bool = Field(
        default=False,
        description=(
            "Team supervisor asserts that the team is done this turn. "
            "Head supervisor uses this to decide whether to call finalizer."
        ),
    )
    content: str = Field(
        default="",
        description=(
            "User-facing answer text. Populate only when next=='FINISH' and "
            "the head supervisor wants to answer the turn itself (simple "
            "greetings, identity, general common-sense). Leave empty when "
            "delegating to a team; downstream workers / finalizer own the "
            "visible response in that case."
        ),
    )


# Status literals attached to a RouterDecision when stored in the graph state.
RouterStatus = Literal["accepted", "rejected_invalid_goto", "parse_failed", "fallback_finish"]


class RouterDecisionRecord(BaseModel):
    """Persisted form of a RouterDecision plus its safeguard outcome."""

    decision: RouterDecision
    status: RouterStatus = "accepted"
    retried: bool = False
