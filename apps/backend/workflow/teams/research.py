from typing import Literal
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langgraph.types import Command
from agent_core.builder import TeamBuilder
from agent_core.state import BaseAgentState
from agent_tools.web import tavily_tool, scrape_webpages
from prompt_kit.prompts import RESEARCHER_PROMPT


class ResearchTeamBuilder(TeamBuilder):
    def register_nodes(self):
        # 1. Search Agent
        search_agent = create_agent(
            model=self.llm,
            tools=[tavily_tool],
            system_prompt=RESEARCHER_PROMPT.template,
        )

        def search_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
            result = search_agent.invoke(state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(
                            content=result["messages"][-1].content, name="search"
                        )
                    ]
                },
                goto="supervisor",
            )

        self.builder.add_node("search", search_node)

        # 2. Web Scraper Agent
        web_scraper_agent = create_agent(
            model=self.llm,
            tools=[scrape_webpages],
            system_prompt=RESEARCHER_PROMPT.template,
        )

        def web_scraper_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
            result = web_scraper_agent.invoke(state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(
                            content=result["messages"][-1].content, name="web_scraper"
                        )
                    ]
                },
                goto="supervisor",
            )

        self.builder.add_node("web_scraper", web_scraper_node)


def get_research_graph(llm):
    return ResearchTeamBuilder(llm, "ResearchTeam", ["search", "web_scraper"]).build()
