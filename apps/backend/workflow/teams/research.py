from agent_core.builder import TeamBuilder
from agent_tools.web import tavily_tool, scrape_webpages
from prompt_kit.prompts import RESEARCHER_PROMPT


class ResearchTeamBuilder(TeamBuilder):
    def register_nodes(self):
        self.add_worker(
            "search",
            tools=[tavily_tool],
            prompt=RESEARCHER_PROMPT.template,
        )
        self.add_worker(
            "web_scraper",
            tools=[scrape_webpages],
            prompt=RESEARCHER_PROMPT.template,
        )


def get_research_graph(llm):
    return ResearchTeamBuilder(llm, "ResearchTeam", ["search", "web_scraper"]).build(
        with_validator=True
    )
