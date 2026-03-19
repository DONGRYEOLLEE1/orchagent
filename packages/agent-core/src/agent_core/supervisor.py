import re
from typing import Literal, List, Callable, Any
from typing_extensions import TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.types import Command
from langgraph.graph import END

from agent_core.state import (
    BaseAgentState,
    build_route_entry,
    normalize_team_name,
)
from prompt_kit.prompts import SYSTEM_SUPERVISOR_PROMPT, TEAM_SUPERVISOR_PROMPT


def _extract_team_stage_sequence(task_plan: str | None) -> list[str]:
    if not task_plan:
        return []

    # More robust regex: handle optional spaces, case-insensitive, and various formats
    # Matches [research_team], [Research Team], [research team] etc.
    stages = re.findall(
        r"\[\s*([a-zA-Z0-9_\s]+(?:_team|team))\s*\]", task_plan, re.IGNORECASE
    )
    compressed: list[str] = []
    for stage in stages:
        normalized = normalize_team_name(stage)
        if not normalized:
            continue
        full_name = f"{normalized}_team"
        if not compressed or compressed[-1] != full_name:
            compressed.append(full_name)
    return compressed


def _extract_completed_team_sequence(route_history: list[Any]) -> list[str]:
    completed: list[str] = []
    for entry in route_history:
        if entry.get("layer") != "team":
            continue
        # Check if the team supervisor returned FINISH
        if entry.get("next") != "FINISH":
            continue
        team = entry.get("team")
        if not team:
            continue
        # Use normalized name to ensure consistency
        normalized = normalize_team_name(team)
        if normalized:
            full_name = f"{normalized}_team"
            if not completed or completed[-1] != full_name:
                completed.append(full_name)
    return completed


def _next_pending_team_stage(
    task_plan: str | None, route_history: list[Any]
) -> str | None:
    planned = _extract_team_stage_sequence(task_plan)
    if not planned:
        return None

    completed = _extract_completed_team_sequence(route_history)

    # Simple sequence tracking: skip already completed stages in order
    completed_index = 0
    for stage in planned:
        if completed_index < len(completed) and completed[completed_index] == stage:
            completed_index += 1
            continue
        return stage

    return None


def make_supervisor_node(
    llm: BaseChatModel,
    members: List[str],
    system_prompt_template: str | None = None,
    *,
    layer: Literal["head", "team"] = "head",
    team_name: str | None = None,
    final_node_name: str | None = None,
    max_team_dispatches: int | None = None,
) -> Callable:
    """
    Creates a supervisor node that manages workflow routing between multiple agents.
    Acts as an intelligent router using Command.
    """
    if not system_prompt_template:
        template = (
            SYSTEM_SUPERVISOR_PROMPT.template
            if layer == "head"
            else TEAM_SUPERVISOR_PROMPT.template
        )
        system_prompt = template.format(members=members)
    else:
        system_prompt = system_prompt_template.format(members=members)

    async def supervisor_node(state: BaseAgentState) -> Command:
        # Create Router class dynamically because of dynamic Literal options
        class Router(TypedDict):
            reasoning: str  # Detailed plan before routing
            next: str
            content: str  # Added to allow supervisor to respond directly
            requires_approval: bool

        print(f"[Supervisor] Processing next turn... Members: {members}", flush=True)
        normalized_team = normalize_team_name(team_name)
        route_history = state.get("route_history", []) or []
        shared_context = state.get("shared_context", {}) or {}
        team_dispatch_count_key = (
            f"{normalized_team}_dispatch_count" if normalized_team else None
        )
        team_dispatch_count = (
            int(shared_context.get(team_dispatch_count_key, 0))
            if team_dispatch_count_key
            else 0
        )

        if layer == "team" and normalized_team and max_team_dispatches is not None:
            if team_dispatch_count >= max_team_dispatches:
                print(
                    f"[Supervisor] {normalized_team} team dispatch limit reached ({team_dispatch_count}/{max_team_dispatches}).",
                    flush=True,
                )
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
                            )
                        ],
                        "messages": [
                            AIMessage(
                                content=(
                                    f"[{normalized_team.capitalize()} Team Limit] Dispatch budget reached. "
                                    "Return to the head supervisor and synthesize with the gathered evidence."
                                ),
                                name="supervisor",
                            )
                        ],
                    },
                    goto=END,
                )

        # Incorporate task_plan into system prompt if it exists
        task_plan = state.get("task_plan", "")
        plan_instruction = (
            (
                f"\n\nCURRENT TASK PLAN:\n{task_plan}\n"
                "Review the plan above and the conversation history. Decide which worker is best suited for the NEXT step of the plan. "
                "If the plan is complete or you can finish it yourself, respond with FINISH."
            )
            if task_plan and task_plan != "NO_PLAN"
            else ""
        )

        system_prompt_plus = f"{system_prompt}{plan_instruction}"

        messages = [{"role": "system", "content": system_prompt_plus}] + state[
            "messages"
        ]
        from typing import cast

        response = cast(
            dict, await llm.with_structured_output(Router).ainvoke(messages)
        )
        reasoning = response.get("reasoning", "")
        next_node = response["next"]
        goto = next_node
        content = response.get("content", "")
        requires_approval = response.get("requires_approval", False)

        print(f"[Supervisor] Routing decision: {goto}", flush=True)
        if reasoning:
            print(f"[Supervisor] Reasoning: {reasoning}", flush=True)
        if content:
            print(f"[Supervisor] Response content: {content[:50]}...", flush=True)

        if requires_approval and layer == "head":
            print(
                f"[Supervisor] Interrupting for user approval. Reasoning: {reasoning}",
                flush=True,
            )
            from langgraph.types import interrupt

            user_feedback = interrupt({"reasoning": reasoning, "goto": goto})

            if user_feedback and isinstance(user_feedback, dict):
                action = user_feedback.get("action")
                feedback_text = user_feedback.get("feedback")

                from langchain_core.messages import HumanMessage

                if action == "reject":
                    reject_msg = (
                        f"User rejected the plan. Feedback: {feedback_text}"
                        if feedback_text
                        else "User rejected the plan."
                    )
                    update_data = {
                        "messages": [
                            AIMessage(
                                content=f"Proposed Plan: {reasoning}", name="supervisor"
                            ),
                            HumanMessage(content=reject_msg),
                        ]
                    }
                    return Command(update=update_data, goto="head_supervisor")
                elif action == "feedback":
                    feedback_msg = (
                        f"User provided feedback on the plan: {feedback_text}"
                    )
                    update_data = {
                        "messages": [
                            AIMessage(
                                content=f"Proposed Plan: {reasoning}", name="supervisor"
                            ),
                            HumanMessage(content=feedback_msg),
                        ]
                    }
                    return Command(update=update_data, goto="head_supervisor")
                # if "approve", fall through to normal routing

        if (
            layer == "head"
            and next_node.endswith("_team")
            and max_team_dispatches is not None
        ):
            next_team_name = normalize_team_name(next_node)
            next_team_dispatch_count = int(
                shared_context.get(f"{next_team_name}_dispatch_count", 0)
            )
            if next_team_dispatch_count >= max_team_dispatches:
                print(
                    f"[Supervisor] Head supervisor stopping further {next_team_name} dispatches after {next_team_dispatch_count} team-level dispatches.",
                    flush=True,
                )
                next_node = "FINISH"
                content = ""

        if layer == "head" and task_plan and task_plan != "NO_PLAN":
            next_planned_stage = _next_pending_team_stage(task_plan, route_history)
            if next_planned_stage:
                if next_node != next_planned_stage:
                    print(
                        f"[Supervisor] Overriding head route {next_node} -> {next_planned_stage} based on task plan progress.",
                        flush=True,
                    )
                next_node = next_planned_stage
                content = ""
            else:
                if next_node != "FINISH":
                    print(
                        f"[Supervisor] Overriding head route {next_node} -> FINISH because all planned stages are complete.",
                        flush=True,
                    )
                next_node = "FINISH"
                content = ""  # Explicitly clear content when plan is complete to avoid mixing with finalizer

        should_use_finalizer = (
            layer == "head"
            and next_node == "FINISH"
            and final_node_name is not None
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

        if should_use_finalizer:
            goto = final_node_name
            content = ""
        elif next_node == "FINISH":
            goto = END
        else:
            goto = next_node

        update_data = {"next": goto}

        if layer == "head":
            next_team = (
                normalize_team_name(next_node)
                if next_node not in {"FINISH", final_node_name}
                else None
            )
            status: Literal["running", "completed"] = (
                "completed"
                if next_node == "FINISH" and not should_use_finalizer
                else "running"
            )
            route_next_node = final_node_name if should_use_finalizer else next_node
            update_data.update(
                {
                    "active_team": next_team,
                    "active_worker": None,
                    "streaming_status": status,
                    "route_history": [
                        build_route_entry(
                            layer="head",
                            node="head_supervisor",
                            next_node=route_next_node or next_node,
                            team=next_team,
                            status=status,
                        )
                    ],
                }
            )
        else:
            next_worker = None if next_node == "FINISH" else next_node
            update_data.update(
                {
                    "active_team": None if next_node == "FINISH" else normalized_team,
                    "active_worker": next_worker,
                    "route_history": [
                        build_route_entry(
                            layer="team",
                            node="supervisor",
                            next_node=next_node,
                            team=normalized_team,
                            worker=next_worker,
                        )
                    ],
                }
            )
            if normalized_team and next_worker is not None:
                update_data["shared_context"] = {
                    f"{normalized_team}_dispatch_count": team_dispatch_count + 1
                }

        if content:
            # Add the supervisor's response to the message history
            update_data["messages"] = [AIMessage(content=content, name="supervisor")]

        return Command(update=update_data, goto=goto)

    return supervisor_node
