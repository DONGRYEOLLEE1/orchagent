from typing import Callable, cast

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
        messages = [{"role": "system", "content": system_prompt}] + state.get(
            "messages", []
        )
        result = cast(
            FinalAnswer,
            await llm.with_structured_output(FinalAnswer).ainvoke(messages),
        )
        final_content = result.content.strip()

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
