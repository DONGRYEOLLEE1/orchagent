from typing import Literal, List, Callable
from typing_extensions import TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import Command
from langgraph.graph import END

from agent_core.state import (
    BaseAgentState,
    build_route_entry,
    normalize_team_name,
)


def make_supervisor_node(
    llm: BaseChatModel,
    members: List[str],
    system_prompt_template: str | None = None,
    *,
    layer: Literal["head", "team"] = "head",
    team_name: str | None = None,
) -> Callable:
    """
    Creates a supervisor node that manages workflow routing between multiple agents.
    Acts as an intelligent router using Command.
    """
    if not system_prompt_template:
        system_prompt = (
            f"You're a supervisor tasked with managing a conversation between the following workers: {members}. "
            "Given the following user request, respond with the worker to act next. "
            "Each worker will perform a task and respond with their results and status. "
            "When finished, respond with FINISH."
        )
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
        system_prompt_plus = (
            f"{system_prompt}\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. You must write a detailed step-by-step plan in the 'reasoning' field before making any routing decision.\n"
            "2. For any questions about current events, news, or topics that require the latest information (e.g., wars, politics, stock market), "
            "you MUST delegate to the 'research_team'. Do not attempt to answer from your own internal knowledge.\n"
            "3. If you can answer simple greetings or general common sense directly, "
            "provide your answer in the 'content' field and set 'next' to 'FINISH'.\n"
            "4. Always prioritize using specialized workers over answering yourself for complex tasks.\n"
            "5. If you receive a [Validation Failed] message from a validator, read the feedback and route the task BACK to the appropriate worker for self-correction.\n"
            "6. If the requested task involves executing code, writing to the filesystem, or any potentially dangerous operation, set 'requires_approval' to true."
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

                from langchain_core.messages import AIMessage, HumanMessage

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

        if goto == "FINISH":
            goto = END

        update_data = {"next": goto}
        normalized_team = normalize_team_name(team_name)

        if layer == "head":
            next_team = (
                normalize_team_name(next_node) if next_node != "FINISH" else None
            )
            status: Literal["running", "completed"] = (
                "completed" if next_node == "FINISH" else "running"
            )
            update_data.update(
                {
                    "active_team": next_team,
                    "active_worker": None,
                    "streaming_status": status,
                    "route_history": [
                        build_route_entry(
                            layer="head",
                            node="head_supervisor",
                            next_node=next_node,
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

        if content:
            # Add the supervisor's response to the message history
            from langchain_core.messages import AIMessage

            update_data["messages"] = [AIMessage(content=content, name="supervisor")]

        return Command(update=update_data, goto=goto)

    return supervisor_node
