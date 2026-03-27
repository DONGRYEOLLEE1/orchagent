import re
from typing import Literal, List, Callable, Any
from typing_extensions import TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.types import Command
from langgraph.graph import END

from agent_core.state import (
    BaseAgentState,
    ResponseMode,
    build_route_entry,
    normalize_team_name,
)
from agent_core.personalization import build_personalization_prompt_block
from prompt_kit.prompts import SYSTEM_SUPERVISOR_PROMPT, TEAM_SUPERVISOR_PROMPT


_APPROVAL_PATTERNS = [
    re.compile(
        r"\b(edit|modify|write|create|delete|remove|rename|overwrite|save|update)\b.*\b(file|files|filesystem|repo|repository|workspace|directory)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(run|execute)\b.*\b(code|script|command|shell|bash|python)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(shell command|bash command|python script|sql script|rm\s+-rf|chmod|chown|drop database|wipe)\b",
        re.IGNORECASE,
    ),
]

_DATA_ANALYSIS_PATTERNS = [
    re.compile(
        r"\b(analy[sz]e|analysis|trend|chart|plot|graph|visuali[sz]e|table|statistics?|aggregate|group by|pivot|forecast|outlier|dataset|csv|xlsx|json|pdf|docx)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(분석|통계|시각화|차트|그래프|추세|집계|피벗|이상치|데이터셋|스프레드시트|엑셀|표)",
        re.IGNORECASE,
    ),
]


def requires_human_approval_for_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _APPROVAL_PATTERNS)


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


def _content_contains_image(content: Any) -> bool:
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "image_url":
                return True

    return False


def _latest_user_request_has_image(messages: list[Any]) -> bool:
    for message in reversed(messages):
        if getattr(message, "type", "") in {"human", "user"}:
            return _content_contains_image(getattr(message, "content", ""))

        if (
            isinstance(message, tuple)
            and len(message) == 2
            and str(message[0]).lower() == "user"
        ):
            return _content_contains_image(message[1])

        if isinstance(message, dict) and message.get("role") == "user":
            return _content_contains_image(message.get("content", ""))

    return False


def _should_force_approval(messages: list[Any]) -> bool:
    latest_user_text = _latest_user_request_text(messages)
    if not latest_user_text:
        return False

    return requires_human_approval_for_text(latest_user_text)


def _shared_context_has_data_attachments(shared_context: dict[str, Any]) -> bool:
    attachments = shared_context.get("attachments") or []
    return any(
        isinstance(attachment, dict)
        and str(attachment.get("kind") or "") in {"pdf", "spreadsheet", "csv", "json", "docx"}
        for attachment in attachments
    )


def _should_force_data_science_team(
    messages: list[Any], shared_context: dict[str, Any]
) -> bool:
    if not _shared_context_has_data_attachments(shared_context):
        return False

    latest_user_text = _latest_user_request_text(messages)
    if not latest_user_text:
        return True

    return any(pattern.search(latest_user_text) for pattern in _DATA_ANALYSIS_PATTERNS)


def _dispatched_team_workers(route_history: list[Any], team_name: str) -> list[str]:
    workers: list[str] = []
    for entry in route_history:
        if entry.get("layer") != "team":
            continue
        if entry.get("team") != team_name:
            continue
        worker = entry.get("worker")
        if worker:
            workers.append(worker)
    return workers


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
                            reasoning=(
                                f"{normalized_team} team dispatch limit reached; returning control."
                            ),
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

        personalization_instruction = build_personalization_prompt_block(shared_context)
        system_prompt_plus = (
            f"{system_prompt}{plan_instruction}{personalization_instruction}"
        )

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
        state_requires_approval = bool(
            shared_context.get("force_requires_approval", False)
        )
        llm_requires_approval = response.get("requires_approval", False)
        heuristic_requires_approval = layer == "head" and _should_force_approval(
            state["messages"]
        )
        requires_approval = (
            llm_requires_approval
            or state_requires_approval
            or heuristic_requires_approval
        )

        discarded_content = ""
        if (state_requires_approval or heuristic_requires_approval) and not llm_requires_approval:
            print(
                "[Supervisor] Heuristic approval guard forced interrupt for a risky user request.",
                flush=True,
            )

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
                if content:
                    discarded_content = content
                next_node = next_planned_stage
                content = ""
            else:
                if next_node != "FINISH":
                    print(
                        f"[Supervisor] Overriding head route {next_node} -> FINISH because all planned stages are complete.",
                        flush=True,
                    )
                if content:
                    discarded_content = content
                next_node = "FINISH"
                content = ""  # Explicitly clear content when plan is complete to avoid mixing with finalizer

        if layer == "team" and normalized_team == "data_science":
            dispatched_workers = _dispatched_team_workers(route_history, normalized_team)
            if "data_engineer" not in dispatched_workers and next_node != "data_engineer":
                next_node = "data_engineer"
                content = ""
            elif (
                "data_engineer" in dispatched_workers
                and "data_analyst" not in dispatched_workers
                and next_node != "data_analyst"
            ):
                next_node = "data_analyst"
                content = ""

        latest_user_has_image = _latest_user_request_has_image(state["messages"])
        data_science_already_routed = bool(
            shared_context.get("data_science_routed_for_current_turn", False)
        )
        if (
            layer == "head"
            and "data_science_team" in members
            and not data_science_already_routed
            and _should_force_data_science_team(state["messages"], shared_context)
        ):
            if not reasoning:
                reasoning = "Attached structured files were detected, so the request is routed to data_science_team for analysis."
            if next_node != "data_science_team":
                print(
                    f"[Supervisor] Forcing head route {next_node} -> data_science_team for file analysis turn.",
                    flush=True,
                )
            if content:
                discarded_content = content
            next_node = "data_science_team"
            content = ""

        if (
            layer == "head"
            and next_node == "research_team"
            and data_science_already_routed
            and _shared_context_has_data_attachments(shared_context)
        ):
            next_node = "FINISH"
            content = ""

        vision_already_routed = bool(
            shared_context.get("vision_routed_for_current_turn", False)
        )
        if (
            layer == "head"
            and "vision_team" in members
            and latest_user_has_image
            and not vision_already_routed
        ):
            if not reasoning:
                reasoning = "An image is attached in the latest user turn, so the request is routed to vision_team first."
            if next_node != "vision_team":
                print(
                    f"[Supervisor] Forcing head route {next_node} -> vision_team for image-bearing user turn.",
                    flush=True,
                )
            if content:
                discarded_content = content
            next_node = "vision_team"
            content = ""

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
            if content:
                discarded_content = content
            content = ""
        elif next_node == "FINISH":
            goto = END
        else:
            goto = next_node

        response_mode: ResponseMode | None = None
        if layer == "head":
            if should_use_finalizer:
                response_mode = "finalizer"
            elif next_node == "FINISH":
                response_mode = "direct"
            else:
                response_mode = "delegated"

        print(f"[Supervisor] Routing decision: {goto}", flush=True)
        if reasoning:
            print(f"[Supervisor] Reasoning: {reasoning}", flush=True)
        if content and response_mode == "direct":
            print(f"[Supervisor] Response content: {content[:50]}...", flush=True)
        elif discarded_content:
            print(
                "[Supervisor] Discarded speculative response content after route override.",
                flush=True,
            )

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
                    "response_mode": response_mode,
                    "streaming_status": status,
                    "route_history": [
                        build_route_entry(
                            layer="head",
                            node="head_supervisor",
                            next_node=route_next_node or next_node,
                            team=next_team,
                            status=status,
                            reasoning=reasoning,
                        )
                    ],
                }
            )
            if next_team == "vision" and latest_user_has_image:
                existing_context = update_data.get("shared_context", {})
                update_data["shared_context"] = {
                    **existing_context,
                    "vision_routed_for_current_turn": True,
                }
            if next_team == "data_science":
                existing_context = update_data.get("shared_context", {})
                update_data["shared_context"] = {
                    **existing_context,
                    "data_science_routed_for_current_turn": True,
                }
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
                            reasoning=reasoning,
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

        if layer == "head" and requires_approval:
            existing_context = update_data.get("shared_context", {})
            update_data["shared_context"] = {
                **existing_context,
                "force_requires_approval": False,
            }

        return Command(update=update_data, goto=goto)

    return supervisor_node
