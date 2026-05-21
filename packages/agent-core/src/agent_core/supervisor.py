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
from agent_core.config import SAFEGUARDS
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

_CODING_PATTERNS = [
    re.compile(
        r"\b(fix|debug|refactor|implement|code|coding|bug|test|tests|build|lint|compile|repo|repository|function|component|module|file|files)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(고쳐|수정|디버그|리팩터|구현|코드|버그|테스트|빌드|린트|레포|저장소|파일|함수|컴포넌트|모듈)",
        re.IGNORECASE,
    ),
]

_RUNTIME_VERIFY_PATTERNS = [
    re.compile(
        r"\b(ui|browser|page|runtime|playwright|e2e|screen|render|rendering|local page)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(화면|브라우저|렌더링|실행 확인|페이지|플레이라이트|e2e|ui)", re.IGNORECASE),
]

# Requests that actually intend to MUTATE the repository. Absent these signals we keep the
# coding_team flow on the explorer-only (read-only) path and skip implementation_engineer entirely.
_CODING_EDIT_INTENT_PATTERNS = [
    re.compile(
        r"\b(fix|debug|refactor|implement|modify|edit|apply|patch|write|add|create|delete|"
        r"remove|rename|rewrite|bump|upgrade|install|replace|update|change|save)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(고쳐|수정|편집|구현|추가|삭제|제거|변경|리팩터|리팩토링|작성|생성|만들|저장|"
        r"교체|업데이트|업그레이드|패치|리네임|이름\s*바꿔)"
    ),
]


def requires_human_approval_for_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _APPROVAL_PATTERNS)


def requires_coding_team_for_text(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _CODING_PATTERNS)


def requires_coding_edit_for_text(text: str) -> bool:
    """Return True when the latest user message expresses intent to modify the repo."""
    return any(pattern.search(text or "") for pattern in _CODING_EDIT_INTENT_PATTERNS)


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


def _shared_context_has_repo_binding(shared_context: dict[str, Any]) -> bool:
    binding = shared_context.get("repo_binding")
    return isinstance(binding, dict) and bool(binding.get("id"))


def _should_force_coding_team(
    messages: list[Any], shared_context: dict[str, Any]
) -> bool:
    if not _shared_context_has_repo_binding(shared_context):
        return False
    latest_user_text = _latest_user_request_text(messages)
    return requires_coding_team_for_text(latest_user_text)


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
            if layer == "head" and task_plan and task_plan != "NO_PLAN"
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
        latest_user_text = _latest_user_request_text(state["messages"])
        orchagent_identity_content = (
            _orchagent_identity_response(latest_user_text)
            if layer == "head" and next_node == "FINISH"
            else None
        )
        if orchagent_identity_content:
            content = orchagent_identity_content
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

        # Safeguard: coding_team's tools are repo-bound and useless without a
        # bound repository. If the LLM still picks coding_team, force FINISH so
        # the head supervisor (or finalizer) can answer directly. This is a
        # final-line guard on top of LLM routing (plan §4.0 P3 — block only,
        # never re-decide the topic).
        if (
            layer == "head"
            and next_node == "coding_team"
            and not shared_context.get("repo_binding")
        ):
            print(
                "[Supervisor] coding_team requested without a bound repository; routing to FINISH for direct LLM answer.",
                flush=True,
            )
            next_node = "FINISH"
            content = ""

        # Safeguard: cap head → same-team redirect streak to avoid ping-pong
        # loops if the LLM keeps re-selecting the same team. Uses the shared
        # `SAFEGUARDS.head_team_redirect_limit` (plan §4.0 P3 — pure safety net).
        if layer == "head" and next_node.endswith("_team"):
            target_team = normalize_team_name(next_node)
            same_team_streak = sum(
                1
                for entry in route_history
                if entry.get("layer") == "head" and entry.get("team") == target_team
            )
            if same_team_streak >= SAFEGUARDS.head_team_redirect_limit:
                print(
                    f"[Supervisor] Head supervisor halting after {same_team_streak} consecutive {next_node} redirects; routing to FINISH.",
                    flush=True,
                )
                next_node = "FINISH"
                content = ""

        allowed_next_nodes = {"FINISH", *members}
        if next_node not in allowed_next_nodes:
            print(
                f"[Supervisor] Invalid routing target {next_node!r} for {layer} layer; coercing to FINISH.",
                flush=True,
            )
            if content:
                discarded_content = content
            next_node = "FINISH"
            content = ""

        should_use_finalizer = (
            layer == "head"
            and next_node == "FINISH"
            and final_node_name is not None
            and not str(content or "").strip()
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
