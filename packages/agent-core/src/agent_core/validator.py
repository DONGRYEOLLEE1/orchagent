from typing import Callable
from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import Command
from langchain_core.messages import AIMessage

from agent_core.state import BaseAgentState


def make_validator_node(
    llm: BaseChatModel,
    team_name: str,
) -> Callable:
    """
    Creates a validator node that checks if the latest worker output fulfills the user request.
    If valid, it routes to 'supervisor'. If invalid, it provides feedback and routes back to the 'supervisor'
    (or directly to a worker if we maintain worker history, but here we let the supervisor re-route based on feedback).
    """

    class ValidationResult(BaseModel):
        is_valid: bool = Field(
            description="True if the output fully answers the request, False otherwise."
        )
        reasoning: str = Field(
            description="Explanation of why it is valid or what is missing."
        )
        feedback: str = Field(
            description="If invalid, specific instructions on what the worker needs to fix or add."
        )

    async def validator_node(state: BaseAgentState) -> Command:
        print(f"[Validator - {team_name}] Checking output...", flush=True)

        system_prompt = (
            f"You are a Quality Assurance Validator for the {team_name}.\n"
            "Your job is to review the conversation history and determine if the latest response from the workers "
            "fully resolves the user's implicit or explicit request.\n"
            "If the response is incomplete, inaccurate, or missing required details, mark it as invalid and provide specific feedback.\n"
            "Do not act as a worker yourself; only evaluate the work done so far."
        )

        messages = [{"role": "system", "content": system_prompt}] + state["messages"]
        from typing import cast

        result = cast(
            ValidationResult,
            await llm.with_structured_output(ValidationResult).ainvoke(messages),
        )

        print(
            f"[Validator - {team_name}] Valid: {result.is_valid}, Reasoning: {result.reasoning}",
            flush=True,
        )

        if result.is_valid:
            return Command(goto="supervisor")
        else:
            # Add the feedback to the state so the supervisor knows it failed
            feedback_message = AIMessage(
                content=f"[Validation Failed] {result.feedback}\nPlease correct the output based on this feedback.",
                name=f"{team_name}_validator",
            )
            return Command(goto="supervisor", update={"messages": [feedback_message]})

    return validator_node
