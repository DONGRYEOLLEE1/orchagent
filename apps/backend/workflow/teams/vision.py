from agent_core.builder import TeamBuilder
from agent_tools.vision import get_image_metadata, resize_image
from prompt_kit.prompts import VISION_ANALYST_PROMPT


class VisionTeamBuilder(TeamBuilder):
    def register_nodes(self):
        self.add_worker(
            "vision_analyst",
            tools=[get_image_metadata, resize_image],
            prompt=VISION_ANALYST_PROMPT.template,
        )


def get_vision_graph(llm):
    return VisionTeamBuilder(llm, "VisionTeam", ["vision_analyst"]).build()
