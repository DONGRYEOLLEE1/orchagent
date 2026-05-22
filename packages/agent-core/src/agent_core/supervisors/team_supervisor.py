"""Team-layer supervisor node factory.

Phase 2.4 of the codebase-wide refactor. A team supervisor is the
internal router for one specialised subgraph (research, writing, vision,
data_science, coding). It:

- Tracks the per-turn ``<team>_dispatch_count`` so it can stop dispatching
  before the cap (avoids worker thrash).
- Asks the LLM router for the next worker; the router applies the
  invalid-goto and dispatch-limit safeguards.
- Writes ``active_team`` / ``active_worker`` and the route entry so the
  SSE layer keeps a coherent view of the turn.
- Never speaks to the end user — team supervisors only route between
  workers and hand control back to the head supervisor.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command

from agent_core.state import (
    BaseAgentState,
    build_route_entry,
    normalize_team_name,
)
from agent_core.supervisors.llm_router import compose_system_prompt, decide_route
from prompt_kit.prompts import TEAM_SUPERVISOR_PROMPT


def make_team_supervisor_node(
    llm: BaseChatModel,
    members: list[str],
    *,
    system_prompt_template: str | None = None,
    team_name: str | None = None,
    max_team_dispatches: int | None = None,
) -> Callable:
    """Factory for a team supervisor node.

    Matches the legacy ``make_supervisor_node`` (``layer="team"``)
    signature surface so existing ``TeamBuilder`` callers do not change.
    """
    template = system_prompt_template or TEAM_SUPERVISOR_PROMPT.template
    base_system_prompt = template.format(members=members)
    normalized_team = normalize_team_name(team_name)
    allowed_nodes: list[str] = list(members)

    async def team_supervisor_node(state: BaseAgentState) -> Command:
        print(
            f"[TeamSupervisor:{normalized_team}] Processing next turn... "
            f"Members: {members}",
            flush=True,
        )

        shared_context = state.get("shared_context", {}) or {}
        team_dispatch_count_key = (
            f"{normalized_team}_dispatch_count" if normalized_team else None
        )

        # Count THIS-TURN dispatches only. The legacy counter in
        # ``shared_context`` accumulates across turns, so on a follow-up
        # turn the team would hit the ceiling on its very first worker
        # dispatch. We recompute from ``route_history`` sliced at the most
        # recent head ``status="completed"`` checkpoint instead.
        route_history = state.get("route_history") or []
        team_dispatch_count = _current_turn_team_dispatches(
            route_history, normalized_team=normalized_team
        )

        # Pre-check dispatch ceiling before paying for an LLM call — saves a
        # round-trip when the team is already saturated this turn.
        if (
            normalized_team
            and max_team_dispatches is not None
            and team_dispatch_count >= max_team_dispatches
        ):
            print(
                f"[TeamSupervisor:{normalized_team}] dispatch limit reached "
                f"({team_dispatch_count}/{max_team_dispatches}).",
                flush=True,
            )
            return _force_finish_due_to_dispatch_limit(
                normalized_team=normalized_team,
            )

        system_prompt = compose_system_prompt(
            base_system_prompt,
            layer="team",
            task_plan=None,  # team supervisors never see the head's task plan
            shared_context=shared_context,
        )

        # Surface worker history to the LLM as a system note so it never has
        # to recompute it from the raw conversation. The LLM still makes the
        # routing decision — this is data, not a rule (plan §4.0 P1).
        worker_history_note = _format_worker_history_note(
            route_history, normalized_team=normalized_team
        )
        if worker_history_note:
            system_prompt = f"{system_prompt}\n\n{worker_history_note}"

        decision, status = await decide_route(
            llm,
            system_prompt=system_prompt,
            messages=state["messages"],
            allowed_nodes=allowed_nodes,
            layer="team",
            dispatch_count=team_dispatch_count,
            max_team_dispatches=max_team_dispatches,
        )

        next_node = decision.next
        goto = END if next_node == "FINISH" else next_node
        next_worker = None if next_node == "FINISH" else next_node

        update_data: dict[str, Any] = {
            "next": goto,
            "active_team": None if next_node == "FINISH" else normalized_team,
            "active_worker": next_worker,
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node=next_node,
                    team=normalized_team,
                    worker=next_worker,
                    reasoning=decision.reason,
                )
            ],
        }

        if normalized_team and next_worker is not None:
            update_data["shared_context"] = {
                f"{normalized_team}_dispatch_count": team_dispatch_count + 1
            }

        _log_decision(decision, goto, status)
        return Command(update=update_data, goto=goto)

    return team_supervisor_node


def _force_finish_due_to_dispatch_limit(*, normalized_team: str) -> Command:
    """Return a FINISH Command when the dispatch ceiling is hit pre-LLM."""
    return Command(
        update={
            "active_team": None,
            "active_worker": None,
            "route_history": [
                build_route_entry(
                    layer="team",
                    node="supervisor",
                    next_node="FINISH",
                    team=normalized_team,
                    reasoning=(
                        f"{normalized_team} team dispatch limit reached; "
                        "returning control."
                    ),
                )
            ],
            "messages": [
                AIMessage(
                    content=(
                        f"[{normalized_team.capitalize()} Team Limit] Dispatch "
                        "budget reached. Return to the head supervisor and "
                        "synthesize with the gathered evidence."
                    ),
                    name="supervisor",
                )
            ],
        },
        goto=END,
    )


def _log_decision(decision: Any, goto: str, status: str) -> None:
    print(f"[TeamSupervisor] Routing decision: {goto}", flush=True)
    if decision.reason:
        print(f"[TeamSupervisor] Reason: {decision.reason}", flush=True)
    if status != "accepted":
        print(f"[TeamSupervisor] Safeguard status: {status}", flush=True)


def _current_turn_team_dispatches(
    route_history: list[dict[str, Any]],
    *,
    normalized_team: str | None,
) -> int:
    """Count this team's worker dispatches IN THIS TURN ONLY.

    The legacy ``<team>_dispatch_count`` field in ``shared_context``
    accumulates across turns, which would trip the dispatch ceiling on a
    follow-up turn's very first worker call. We recompute from the
    ``route_history`` slice that comes after the most recent head
    ``status="completed"`` so the count is turn-local.
    """
    if not normalized_team or not route_history:
        return 0
    last_completed_idx = -1
    for idx, entry in enumerate(route_history):
        if entry.get("layer") == "head" and entry.get("status") == "completed":
            last_completed_idx = idx
    current_turn = (
        route_history[last_completed_idx + 1 :]
        if last_completed_idx >= 0
        else route_history
    )
    count = 0
    for entry in current_turn:
        if entry.get("layer") != "team":
            continue
        if entry.get("team") != normalized_team:
            continue
        worker = entry.get("worker")
        if isinstance(worker, str) and worker and worker != "FINISH":
            count += 1
    return count


def _format_worker_history_note(
    route_history: list[dict[str, Any]],
    *,
    normalized_team: str | None,
) -> str | None:
    """Summarize this team's worker history split by turn boundary.

    Multi-turn threads accumulate ``route_history`` across turns. The team
    supervisor's worker-selection LLM needs both pieces of context:

    1. Prior-turn workers — so it knows the team already ran (and which
       brief/analysis is already on the conversation), useful for
       follow-up requests like "same data, different chart".
    2. This-turn workers — so it never repeats a worker that already ran
       in the current turn.

    Returns ``None`` when there is nothing meaningful to report.
    """
    if not normalized_team or not route_history:
        return None

    # Slice the history at the most recent head ``status="completed"``;
    # entries before that index belong to previous turns.
    last_completed_idx = -1
    for idx, entry in enumerate(route_history):
        if entry.get("layer") == "head" and entry.get("status") == "completed":
            last_completed_idx = idx

    if last_completed_idx >= 0:
        previous_turn = route_history[: last_completed_idx + 1]
        current_turn = route_history[last_completed_idx + 1 :]
    else:
        previous_turn = []
        current_turn = list(route_history)

    def _team_worker_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in entries:
            if entry.get("layer") != "team":
                continue
            if entry.get("team") != normalized_team:
                continue
            worker = entry.get("worker")
            if isinstance(worker, str) and worker and worker != "FINISH":
                counts[worker] = counts.get(worker, 0) + 1
        return counts

    prev_counts = _team_worker_counts(previous_turn)
    curr_counts = _team_worker_counts(current_turn)
    if not prev_counts and not curr_counts:
        return None

    def _summary(counts: dict[str, int]) -> str:
        return ", ".join(
            f"{worker} ({count} call{'s' if count > 1 else ''})"
            for worker, count in counts.items()
        )

    lines = ["# TEAM WORKER HISTORY"]
    if prev_counts:
        lines.append(
            f"- Previous turns (already produced briefs/analyses you can "
            f"build on): {_summary(prev_counts)}."
        )
    if curr_counts:
        lines.append(
            f"- This turn so far: {_summary(curr_counts)}."
        )
        lines.append(
            "- A worker that already ran in THIS TURN cannot be dispatched"
            " again unless the Reviewer feedback names a concrete code-level"
            " gap only that worker can fix. Route to the NEXT worker in the"
            " workflow."
        )
    else:
        lines.append(
            "- Nothing dispatched yet in this turn — start with the worker"
            " that owns the new request (the engineer briefs/inspects, the"
            " analyst computes and renders charts)."
        )
    return "\n".join(lines)


__all__ = ["make_team_supervisor_node"]
