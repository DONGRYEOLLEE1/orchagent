from agent_core.builder import TeamBuilder
from agent_tools.web import tavily_tool, scrape_webpages
from core.config import settings
from prompt_kit.prompts import (
    RESEARCH_TEAM_SUPERVISOR_PROMPT,
    SEARCH_WORKER_PROMPT,
    WEB_SCRAPER_PROMPT,
)


class ResearchTeamBuilder(TeamBuilder):
    def register_nodes(self):
        self.add_worker(
            "search",
            tools=[tavily_tool],
            prompt=SEARCH_WORKER_PROMPT.template,
        )
        self.add_worker(
            "web_scraper",
            tools=[scrape_webpages],
            prompt=WEB_SCRAPER_PROMPT.template,
        )


def get_research_graph(llm):
    # Research keeps a dedicated supervisor contract because its workers have a
    # natural evidence-gathering order: search first, scrape only when needed.
    return ResearchTeamBuilder(llm, "ResearchTeam", ["search", "web_scraper"]).build(
        with_validator=True,
        max_team_dispatches=settings.RESEARCH_TEAM_MAX_DISPATCHES,
        system_prompt_template=RESEARCH_TEAM_SUPERVISOR_PROMPT.template,
    )
