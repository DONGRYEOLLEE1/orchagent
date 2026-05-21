"""Head-layer supervisor node factory.

Phase 2.4 of the codebase-wide refactor. The head supervisor is the
top-of-graph router that:

- Asks the LLM-driven router (:mod:`agent_core.supervisors.llm_router`)
  which team should run next.
- Optionally pauses for human approval via ``langgraph.types.interrupt``
  when the LLM raises ``request_review`` or the state flag
  ``force_requires_approval`` is set.
- Picks the finalizer over a raw FINISH when synthesis is appropriate.
- Enforces the per-team redirect safeguard via the LLM router.
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


# ---------------------------------------------------------------------------
# Helpers — lifted from the previous monolithic supervisor.py so the head
# layer can answer identity questions deterministically before falling back
# to the LLM-emitted content. These are pure utilities (no graph state).
# ---------------------------------------------------------------------------


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return " ".join(part for part in parts if part)
    return str(content or "")


def _latest_user_request_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") in {"human", "user"}:
            return _extract_message_text(getattr(message, "content", ""))
        if (
            isinstance(message, tuple)
            and len(message) == 2
            and str(message[0]).lower() == "user"
        ):
            return _extract_message_text(message[1])
        if isinstance(message, dict) and message.get("role") == "user":
            return _extract_message_text(message.get("content", ""))
    return ""


def _orchagent_identity_response(user_text: str) -> str | None:
    """Deterministic identity answer so the model never invents a name."""
    normalized = user_text.strip().lower()
    if not normalized:
        return None

    name_patterns = (
        "너 이름",
        "네 이름",
        "이름이 뭐",
        "what is your name",
        "your name",
        "who are you",
    )
    identity_patterns = (
        "너 정체",
        "네 정체",
        "정체가 뭐",
        "what are you",
        "who are you really",
        "what is orchagent",
    )

    if any(pattern in normalized for pattern in name_patterns):
        return "저는 OrchAgent입니다."
    if any(pattern in normalized for pattern in identity_patterns):
        return "저는 여러 전문 팀을 오케스트레이션하는 OrchAgent입니다."
    return None


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

        # ---- Coding team safeguard: needs repo binding. -------------------
        next_node = decision.next
        if next_node == "coding_team" and not shared_context.get("repo_binding"):
            print(
                "[HeadSupervisor] coding_team requested without a bound repository; "
                "routing to FINISH for direct LLM answer.",
                flush=True,
            )
            next_node = "FINISH"

        # ---- Direct-FINISH answer content. ------------------------------
        # Priority:
        #   1. Deterministic identity override (so the model never invents a
        #      name for "who are you" style turns).
        #   2. LLM-emitted ``RouterDecision.content`` for simple turns the
        #      head supervisor decided to answer itself (regression fix:
        #      after the Phase 2.4 head/team split, FINISH was emitting an
        #      empty AI message because content was no longer in scope).
        content: str | None = None
        if next_node == "FINISH":
            latest_user_text = _latest_user_request_text(state["messages"])
            content = _orchagent_identity_response(latest_user_text)
            if not content and decision.content and decision.content.strip():
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
        status_label: Literal["running", "completed"] = (
            "completed"
            if next_node == "FINISH" and not should_use_finalizer
            else "running"
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
                    status=status_label,
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
    """Largest streak of consecutive head-layer redirects to the same team."""
    streaks: dict[str, int] = {}
    for entry in route_history:
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
