from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START
from langgraph.types import Command

from agent_core.state import BaseAgentState
from agent_core.supervisor import make_supervisor_node
from workflow.teams.research import get_research_graph
from workflow.teams.writing import get_writing_graph

def get_orchagent_graph(llm_model: str = "gpt-4o-mini"):
    llm = ChatOpenAI(model=llm_model)
    
    # 1. Subgraphs
    research_graph = get_research_graph(llm)
    writing_graph = get_writing_graph(llm)

    # 2. Team Wrapper Nodes
    def call_research_team(state: BaseAgentState) -> Command[Literal["head_supervisor"]]:
        # Subgraph invocation
        result = research_graph.invoke({"messages": state['messages']})
        return Command(
            update={"messages": [HumanMessage(content=result['messages'][-1].content, name="research_team")]},
            goto="head_supervisor"
        )

    def call_paper_writing_team(state: BaseAgentState) -> Command[Literal["head_supervisor"]]:
        # Subgraph invocation
        result = writing_graph.invoke({"messages": state['messages']})
        return Command(
            update={"messages": [HumanMessage(content=result['messages'][-1].content, name="writing_team")]},
            goto="head_supervisor"
        )

    # 3. Head Supervisor
    head_supervisor_node = make_supervisor_node(llm, ["research_team", "writing_team"])

    # 4. Build Super Graph
    builder = StateGraph(BaseAgentState)
    builder.add_node("head_supervisor", head_supervisor_node)
    builder.add_node("research_team", call_research_team)
    builder.add_node("writing_team", call_paper_writing_team)
    
    builder.add_edge(START, "head_supervisor")
    
    return builder
