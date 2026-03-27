from typing import Callable

from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command

from agent_core.state import BaseAgentState, build_route_entry
from agent_core.personalization import build_personalization_prompt_block
from prompt_kit.prompts import FINALIZER_PROMPT


class FinalAnswer(BaseModel):
    content: str = Field(description="The final end-user-facing answer only.")


def _dedupe_consecutive_ai_messages(messages: list[object]) -> list[object]:
    deduped: list[object] = []
    previous_signature: tuple[str | None, str | None] | None = None

    for message in messages:
        if isinstance(message, AIMessage):
            signature = (message.name, str(message.content))
            if deduped and previous_signature == signature:
                continue
            previous_signature = signature
        else:
            previous_signature = None
        deduped.append(message)

    return deduped


def _extract_review_approved_worker_output(messages: list[object]) -> str:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, AIMessage):
            continue
        content = str(message.content or "").strip()
        if not content.startswith("[Review Passed]"):
            continue

        for previous in range(index - 1, -1, -1):
            candidate = messages[previous]
            if not isinstance(candidate, AIMessage):
                continue
            if candidate.name in {"supervisor", "planner", "reviewer"}:
                continue
            candidate_content = str(candidate.content or "").strip()
            if candidate_content:
                return candidate_content
        break

    return ""


def make_finalizer_node(llm: BaseChatModel) -> Callable:
    system_prompt = FINALIZER_PROMPT.template

    async def finalizer_node(state: BaseAgentState) -> Command:
        print("[Finalizer] Synthesizing final answer...", flush=True)
        shared_context = state.get("shared_context", {}) or {}
        review_approved_content = _extract_review_approved_worker_output(
            state.get("messages", [])
        )
        if review_approved_content:
            print(
                "[Finalizer] Using review-approved worker output without additional synthesis.",
                flush=True,
            )
            return Command(
                update={
                    "messages": [AIMessage(content=review_approved_content, name="assistant")],
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

        system_prompt_plus = f"{system_prompt}{build_personalization_prompt_block(shared_context)}"
        messages = [{"role": "system", "content": system_prompt_plus}] + _dedupe_consecutive_ai_messages(
            state.get("messages", [])
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
