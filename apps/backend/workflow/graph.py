from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from agent_core.state import BaseAgentState
from agent_core.supervisor import make_supervisor_node
from agent_tools.web import tavily_tool, scrape_webpages
from agent_tools.file_io import create_outline, read_document, write_document, edit_document, python_repl_tool

llm = ChatOpenAI(model="gpt-4o-mini")

# --- Research Team ---
search_agent = create_react_agent(model=llm, tools=[tavily_tool])
def search_node(state: BaseAgentState) -> Command[Literal['supervisor']]:
    result = search_agent.invoke(state)
    return Command(
        update={"messages": [HumanMessage(content=result['messages'][-1].content, name="search")]},
        goto='supervisor'
    )

web_scraper_agent = create_react_agent(llm, tools=[scrape_webpages])
def web_scraper_node(state: BaseAgentState) -> Command[Literal['supervisor']]:
    result = web_scraper_agent.invoke(state)
    return Command(
        update={"messages": [HumanMessage(content=result['messages'][-1].content, name="web_scraper")]},
        goto="supervisor"
    )

research_supervisor_node = make_supervisor_node(llm, ["search", "web_scraper"])

research_builder = StateGraph(BaseAgentState)
research_builder.add_node("supervisor", research_supervisor_node)
research_builder.add_node("search", search_node)
research_builder.add_node("web_scraper", web_scraper_node)
research_builder.add_edge(START, "supervisor")
research_graph = research_builder.compile()

# --- Writing Team ---
doc_writer_agent = create_react_agent(
    model=llm,
    tools=[write_document, edit_document, read_document],
    prompt="You can read, write and edit documents based on note-taker's outlines. Don't ask follow-up questions."
)
def doc_writing_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
    result = doc_writer_agent.invoke(state)
    return Command(
        update={"messages": [HumanMessage(content=result['messages'][-1].content, name="doc_writer")]},
        goto="supervisor"
    )

note_taking_agent = create_react_agent(
    model=llm,
    tools=[create_outline, read_document],
    prompt="You can read documents and create outlines for the document writer. Don't ask follow-up questions."
)
def note_taking_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
    result = note_taking_agent.invoke(state)
    return Command(
        update={"messages": [HumanMessage(content=result['messages'][-1].content, name="note_taker")]},
        goto="supervisor"
    )

chart_generating_agent = create_react_agent(
    model=llm,
    tools=[read_document, python_repl_tool]
)
def chart_generating_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
    result = chart_generating_agent.invoke(state)
    return Command(
        update={"messages": [HumanMessage(content=result['messages'][-1].content, name="chart_generator")]},
        goto="supervisor"
    )

doc_writing_supervisor_node = make_supervisor_node(llm, ["doc_writer", "note_taker", "chart_generator"])

paper_writing_builder = StateGraph(BaseAgentState)
paper_writing_builder.add_node("supervisor", doc_writing_supervisor_node)
paper_writing_builder.add_node("doc_writer", doc_writing_node)
paper_writing_builder.add_node("note_taker", note_taking_node)
paper_writing_builder.add_node("chart_generator", chart_generating_node)
paper_writing_builder.add_edge(START, "supervisor")
paper_writing_graph = paper_writing_builder.compile()

# --- Head Supervisor ---
def call_research_team(state: BaseAgentState) -> Command[Literal["head_supervisor"]]:
    result = research_graph.invoke({"messages": state['messages'][-1].content})
    return Command(
        update={"messages": [HumanMessage(content=result['messages'][-1].content, name="research_team")]},
        goto="head_supervisor"
    )

def call_paper_writing_team(state: BaseAgentState) -> Command[Literal["head_supervisor"]]:
    result = paper_writing_graph.invoke({"messages": state['messages'][-1].content})
    return Command(
        update={"messages": [HumanMessage(content=result['messages'][-1].content, name="writing_team")]},
        goto="head_supervisor"
    )

teams_supervisor_node = make_supervisor_node(llm, ["research_team", "writing_team"])

super_builder = StateGraph(BaseAgentState)
super_builder.add_node("head_supervisor", teams_supervisor_node)
super_builder.add_node("research_team", call_research_team)
super_builder.add_node("writing_team", call_paper_writing_team)
super_builder.add_edge(START, "head_supervisor")

# Optional: Add checkpointer later
orchagent_graph = super_builder.compile()
