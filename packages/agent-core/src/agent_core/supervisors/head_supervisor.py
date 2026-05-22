"""Head-layer supervisor node factory.

Phase 2.4 of the codebase-wide refactor. The head supervisor is the
top-of-graph router that:

- Asks the LLM-driven router (:mod:`agent_core.supervisors.llm_router`)
  which team should run next.
- Optionally pauses for human approval via ``langgraph.types.interrupt``
  when the LLM raises ``request_review`` or the state flag
  ``force_requires_approval`` is set.
- Picks the finalizer over a raw FINISH when synthesis is appropriate.
- Enforces head-layer safeguards via the LLM router.
- Writes the routing decision into the persistent ``route_history`` so
  the SSE layer can emit ``route`` events without re-deriving it.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END
from langgraph.types import Command

from agent_core.state import (
    BaseAgentState,
    ResponseMode,
    build_route_entry,
    normalize_team_name,
)
from agent_core.supervisors.llm_router import compose_system_prompt, decide_route
from prompt_kit.prompts import SYSTEM_SUPERVISOR_PROMPT


def make_head_supervisor_node(
    llm: BaseChatModel,
    members: list[str],
    *,
    system_prompt_template: str | None = None,
    final_node_name: str | None = None,
    max_team_dispatches: int | None = None,
) -> Callable:
    """Factory for the head supervisor node.

    Keeps the same signature surface the legacy ``make_supervisor_node``
    used to expose for ``layer="head"`` so callers in ``main_graph.py``
    do not change.
    """
    template = system_prompt_template or SYSTEM_SUPERVISOR_PROMPT.template
    base_system_prompt = template.format(members=members)
    allowed_nodes: list[str] = list(members)

    async def head_supervisor_node(state: BaseAgentState) -> Command:
        print(
            f"[HeadSupervisor] Processing next turn... Members: {members}",
            flush=True,
        )

        shared_context = state.get("shared_context", {}) or {}
        route_history = state.get("route_history", []) or []
        task_plan = state.get("task_plan", "")

        system_prompt = compose_system_prompt(
            base_system_prompt,
            layer="head",
            task_plan=task_plan,
            shared_context=shared_context,
        )

        # Count consecutive same-team redirects so the LLM router can apply
        # the head_team_redirect_limit safeguard without having to look at
        # state itself. We over-count here (head router will recompute per
        # candidate team) but the safeguard is still safe — it forces FINISH
        # only when the streak meets the limit.
        same_team_streak = _max_same_team_streak(route_history)

        decision, status = await decide_route(
            llm,
            system_prompt=system_prompt,
            messages=state["messages"],
            allowed_nodes=allowed_nodes,
            layer="head",
            same_team_streak=same_team_streak,
        )

        # ---- HITL: interrupt only when LLM (or state flag) asked for it. --
        state_requires_approval = bool(
            shared_context.get("force_requires_approval", False)
        )
        requires_approval = decision.request_review or state_requires_approval
        if requires_approval:
            interrupt_result = _maybe_interrupt(decision)
            if interrupt_result is not None:
                return interrupt_result

        next_node = decision.next

        # ---- Direct-FINISH answer content. ------------------------------
        # Plan §4.0 P1/P3: the head supervisor LLM owns the final-answer
        # content for direct-FINISH turns. Identity questions are handled
        # by the SYSTEM_SUPERVISOR_PROMPT (IDENTITY block) so the model
        # itself answers as OrchAgent — no rule-based override.
        content: str | None = None
        if next_node == "FINISH" and decision.content and decision.content.strip():
            content = decision.content

        # ---- Decide whether to invoke the finalizer instead of raw END. --
        should_use_finalizer = (
            next_node == "FINISH"
            and final_node_name is not None
            and not (content or "").strip()
            and (
                (task_plan and task_plan != "NO_PLAN")
                or any(
                    entry.get("layer") == "team"
                    or (
                        entry.get("layer") == "head"
                        and entry.get("next") not in {None, "FINISH"}
                    )
                    for entry in route_history
                )
            )
        )

        goto: str
        response_mode: ResponseMode | None
        if should_use_finalizer and final_node_name is not None:
            goto = final_node_name
            response_mode = "finalizer"
        elif next_node == "FINISH":
            goto = END
            response_mode = "direct"
        else:
            goto = next_node
            response_mode = "delegated"

        next_team = (
            normalize_team_name(next_node)
            if next_node not in {"FINISH", final_node_name}
            else None
        )
        # Turn boundary: both raw FINISH and finalizer routes end the current
        # turn from the user's perspective. We label both as "completed" so
        # ``route_history`` slicing in follow-up turns can isolate this-turn
        # entries via the most recent ``status="completed"`` head checkpoint.
        # ``streaming_status`` keeps the legacy "running" semantics so the SSE
        # consumer still sees the finalizer phase as in-flight.
        is_turn_end = next_node == "FINISH"
        status_label: Literal["running", "completed"] = (
            "completed" if is_turn_end and not should_use_finalizer else "running"
        )
        route_status_label: Literal["running", "completed"] = (
            "completed" if is_turn_end else "running"
        )
        route_next_node = final_node_name if should_use_finalizer else next_node

        update_data: dict[str, Any] = {
            "next": goto,
            "active_team": next_team,
            "active_worker": None,
            "response_mode": response_mode,
            "streaming_status": status_label,
            "route_history": [
                build_route_entry(
                    layer="head",
                    node="head_supervisor",
                    next_node=route_next_node or next_node,
                    team=next_team,
                    status=route_status_label,
                    reasoning=decision.reason,
                )
            ],
        }

        if content:
            update_data["messages"] = [AIMessage(content=content, name="supervisor")]

        if requires_approval:
            update_data["shared_context"] = {"force_requires_approval": False}

        _log_decision(decision, goto, status, response_mode, content)
        return Command(update=update_data, goto=goto)

    return head_supervisor_node


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _max_same_team_streak(route_history: Iterable[dict[str, Any]]) -> int:
    """Largest streak of head-layer redirects to the same team in THIS turn.

    Multi-turn threads accumulate ``route_history`` across turns. Counting
    every prior turn's head→team entry would push the streak past the
    safeguard limit on the very first head call of a new turn, even when
    nothing has actually looped this turn. We slice to entries after the
    most recent head ``status="completed"`` checkpoint (which marks the end
    of the previous turn) so the streak reflects only the current turn.
    """
    history_list = list(route_history)
    last_completed_idx = -1
    for idx, entry in enumerate(history_list):
        if entry.get("layer") == "head" and entry.get("status") == "completed":
            last_completed_idx = idx
    current_turn = (
        history_list[last_completed_idx + 1 :]
        if last_completed_idx >= 0
        else history_list
    )
    streaks: dict[str, int] = {}
    for entry in current_turn:
        if entry.get("layer") != "head":
            continue
        team = entry.get("team")
        if not team:
            continue
        streaks[team] = streaks.get(team, 0) + 1
    return max(streaks.values()) if streaks else 0


def _maybe_interrupt(decision: Any) -> Command | None:
    """Pause via ``interrupt`` and translate the user's response to a Command.

    Returns ``None`` when the user approves so the caller can keep
    routing normally. Returns a fully-formed ``Command`` when the user
    rejects or sends feedback so we bounce back to the head supervisor.
    """
    print(
        f"[HeadSupervisor] Interrupting for user approval. Reasoning: {decision.reason}",
        flush=True,
    )
    from langgraph.types import interrupt  # noqa: WPS433 (local import for monkeypatching)

    user_feedback = interrupt(
        {"reasoning": decision.reason, "goto": decision.next}
    )
    if not user_feedback or not isinstance(user_feedback, dict):
        return None
    action = user_feedback.get("action")
    feedback_text = user_feedback.get("feedback")

    if action == "reject":
        reject_msg = (
            f"User rejected the plan. Feedback: {feedback_text}"
            if feedback_text
            else "User rejected the plan."
        )
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content=f"Proposed Plan: {decision.reason}",
                        name="supervisor",
                    ),
                    HumanMessage(content=reject_msg),
                ]
            },
            goto="head_supervisor",
        )
    if action == "feedback":
        feedback_msg = f"User provided feedback on the plan: {feedback_text}"
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content=f"Proposed Plan: {decision.reason}",
                        name="supervisor",
                    ),
                    HumanMessage(content=feedback_msg),
                ]
            },
            goto="head_supervisor",
        )
    return None  # "approve" or unknown action falls through to normal routing


def _log_decision(
    decision: Any,
    goto: str,
    status: str,
    response_mode: ResponseMode | None,
    content: str | None,
) -> None:
    print(f"[HeadSupervisor] Routing decision: {goto}", flush=True)
    if decision.reason:
        print(f"[HeadSupervisor] Reason: {decision.reason}", flush=True)
    if status != "accepted":
        print(f"[HeadSupervisor] Safeguard status: {status}", flush=True)
    if content and response_mode == "direct":
        print(
            f"[HeadSupervisor] Direct response content: {content[:60]}...",
            flush=True,
        )


__all__ = ["make_head_supervisor_node"]
