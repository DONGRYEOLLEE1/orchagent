from typing import Literal
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langgraph.types import Command
from agent_core.builder import TeamBuilder
from agent_core.state import BaseAgentState
from agent_tools.vision import get_image_metadata, resize_image
from prompt_kit.prompts import VISION_ANALYST_PROMPT


class VisionTeamBuilder(TeamBuilder):
    def register_nodes(self):
        # 1. Vision Analyst Agent
        # This agent uses VLM capabilities of the underlying model
        vision_analyst_agent = create_agent(
            model=self.llm,
            tools=[get_image_metadata, resize_image],
            system_prompt=VISION_ANALYST_PROMPT.template,
        )

        def vision_analyst_node(
            state: BaseAgentState,
        ) -> Command[Literal["supervisor"]]:
            result = vision_analyst_agent.invoke(state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(
                            content=result["messages"][-1].content,
                            name="vision_analyst",
                        )
                    ]
                },
                goto="supervisor",
            )

        self.builder.add_node("vision_analyst", vision_analyst_node)


def get_vision_graph(llm):
    return VisionTeamBuilder(llm, "VisionTeam", ["vision_analyst"]).build()
