"""Safety-net constants for the LangGraph supervisor + validator nodes.

Phase 2.1 of the codebase-wide refactor. These values used to live as
module-level literals inside ``supervisor.py`` / ``validator.py`` / the
team builders. Pulling them into one place makes the LLM-Driven Routing
policy (plan §4.0) crisp:

- The constants here are **safety nets**, not routing policy. They never
  change what the LLM decides; they only short-circuit pathological loops.
- LLM routing decisions live in prompt-kit + ``LLMRouter`` (Phase 2.4/2.5).
- All values can be overridden by env via ``settings`` if needed.

Tunable via ``core.config.settings`` overrides in apps/backend; the defaults
mirror the pre-refactor behaviour exactly so nothing changes at the moment
of extraction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingSafeguards:
    """Bounded counters that force-finish a turn instead of looping forever."""

    # Same team is re-routed to from head supervisor at most this many times
    # before a forced FINISH. Mirrors the previous ``HEAD_TEAM_REDIRECT_LIMIT``.
    head_team_redirect_limit: int = 2

    # Reviewer (validator) recursion ceiling. Mirrors the previous
    # ``remaining_steps`` literal in ``validator.py``.
    validator_remaining_steps: int = 100

    # Max number of worker dispatches a team supervisor may issue per turn.
    # Used by ``TeamBuilder``; previously a magic argument.
    max_team_dispatches: int = 8

    # When the LLM emits a structured output that fails to parse, retry this
    # many times before falling back to FINISH.
    structured_output_retry_count: int = 1


# Single import point used throughout agent_core / workflow.
SAFEGUARDS = RoutingSafeguards()
