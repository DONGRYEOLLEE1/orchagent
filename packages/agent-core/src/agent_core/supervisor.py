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
            next: str
            content: str  # Added to allow supervisor to respond directly

        print(f"[Supervisor] Processing next turn... Members: {members}", flush=True)
        system_prompt_plus = (
            f"{system_prompt}\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. For any questions about current events, news, or topics that require the latest information (e.g., wars, politics, stock market), "
            "you MUST delegate to the 'research_team'. Do not attempt to answer from your own internal knowledge.\n"
            "2. If you can answer simple greetings or general common sense directly, "
            "provide your answer in the 'content' field and set 'next' to 'FINISH'.\n"
            "3. Always prioritize using specialized workers over answering yourself for complex tasks."
        )

        messages = [{"role": "system", "content": system_prompt_plus}] + state[
            "messages"
        ]
        response = await llm.with_structured_output(Router).ainvoke(messages)
        next_node = response["next"]  # type: ignore
        goto = next_node
        content = response.get("content", "")  # type: ignore

        print(f"[Supervisor] Routing decision: {goto}", flush=True)
        if content:
            print(f"[Supervisor] Response content: {content[:50]}...", flush=True)

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
