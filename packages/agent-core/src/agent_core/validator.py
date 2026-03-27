from typing import Callable
from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import Command
from langchain_core.messages import AIMessage
from prompt_kit.prompts import REVIEWER_PROMPT

from agent_core.state import BaseAgentState


def make_reviewer_node(
    llm: BaseChatModel,
    team_name: str,
) -> Callable:
    """
    Creates a reviewer/critic node that rigorously checks if the latest worker output fulfills the user request.
    If valid, it routes to 'supervisor'. If invalid, it provides detailed critique and routes back to the 'supervisor'.
    """

    class ReviewResult(BaseModel):
        is_valid: bool = Field(
            description="True if the output is perfect and fully resolves the request, False otherwise."
        )
        critique: str = Field(
            description="Detailed critical evaluation of the output, identifying missing points, logical errors, or hallucinations."
        )
        feedback: str = Field(
            description="Specific instructions for the worker to improve the output."
        )

    async def reviewer_node(state: BaseAgentState) -> Command:
        print(f"[Reviewer - {team_name}] Critiquing output...", flush=True)

        system_prompt = REVIEWER_PROMPT.template.format(team_name=team_name)

        messages = [{"role": "system", "content": system_prompt}] + state.get(
            "messages", []
        )
        from typing import cast

        # Edge Case 1: 무한 자가 수정 루프 방지 (Infinite Correction Loop)
        remaining_steps = state.get("remaining_steps", 100)
        if remaining_steps <= 1:
            print(
                f"[Reviewer - {team_name}] Recursion limit reached. Halting loop.",
                flush=True,
            )
            fallback_message = AIMessage(
                content="[Review Warning] Maximum correction steps reached. Output might be incomplete.",
                name=f"{team_name}_reviewer",
            )
            return Command(goto="supervisor", update={"messages": [fallback_message]})

        try:
            result = cast(
                ReviewResult,
                await llm.with_structured_output(ReviewResult).ainvoke(messages),
            )
        except Exception as e:
            # Edge Case 2: Validator의 환각 (Validator Hallucination)
            print(
                f"[Reviewer - {team_name}] Error parsing review result: {e}",
                flush=True,
            )
            fallback_message = AIMessage(
                content="[Review Error] System encountered an error during review. Proceeding safely.",
                name=f"{team_name}_reviewer",
            )
            return Command(goto="supervisor", update={"messages": [fallback_message]})

        print(
            f"[Reviewer - {team_name}] Valid: {result.is_valid}, Critique: {result.critique[:100]}...",
            flush=True,
        )

        if result.is_valid:
            passed_message = AIMessage(
                content="[Review Passed] Output materially satisfies the request.",
                name=f"{team_name}_reviewer",
            )
            return Command(goto="supervisor", update={"messages": [passed_message]})
        else:
            # Add the critique and feedback to the state so the supervisor knows it failed
            feedback_message = AIMessage(
                content=f"[Review Failed]\n**Critique:** {result.critique}\n**Feedback:** {result.feedback}\n\nPlease correct the output based on this feedback.",
                name=f"{team_name}_reviewer",
            )
            return Command(goto="supervisor", update={"messages": [feedback_message]})

    return reviewer_node


# Maintain alias for backward compatibility during transition
make_validator_node = make_reviewer_node
