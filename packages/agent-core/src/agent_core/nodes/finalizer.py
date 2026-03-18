from typing import Callable

from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command

from agent_core.state import BaseAgentState, build_route_entry
from prompt_kit.prompts import FINALIZER_PROMPT


class FinalAnswer(BaseModel):
    content: str = Field(description="The final end-user-facing answer only.")


def make_finalizer_node(llm: BaseChatModel) -> Callable:
    system_prompt = FINALIZER_PROMPT.template

    async def finalizer_node(state: BaseAgentState) -> Command:
        print("[Finalizer] Synthesizing final answer...", flush=True)
        messages = [{"role": "system", "content": system_prompt}] + state.get(
            "messages", []
        )

        try:
            from typing import cast

            result = cast(
                FinalAnswer,
                await llm.with_structured_output(FinalAnswer).ainvoke(messages),
            )
            final_content = result.content.strip()
        except Exception as e:
            print(
                f"[Finalizer] Error during structured output: {e}. Falling back to last message.",
                flush=True,
            )
            final_content = ""

        # Fallback: If final_content is empty, try to get the last assistant message that is NOT from supervisor/planner
        if not final_content:
            all_msgs = state.get("messages", [])
            for msg in reversed(all_msgs):
                if isinstance(msg, AIMessage) and msg.name not in {
                    "supervisor",
                    "planner",
                    "reviewer",
                }:
                    if msg.content and isinstance(msg.content, str):
                        final_content = msg.content.strip()
                        if final_content:
                            print(
                                f"[Finalizer] Fallback used content from worker: {msg.name}",
                                flush=True,
                            )
                            break

            # Absolute fallback
            if not final_content:
                final_content = "I'm sorry, I couldn't synthesize a final answer. Please check the tool activity for details."

        return Command(
            update={
                "messages": [AIMessage(content=final_content, name="assistant")],
                "active_team": None,
                "active_worker": None,
                "streaming_status": "completed",
                "route_history": [
                    build_route_entry(
                        layer="head",
                        node="finalizer",
                        next_node="FINISH",
                        status="completed",
                    )
                ],
            },
            goto=END,
        )

    return finalizer_node
