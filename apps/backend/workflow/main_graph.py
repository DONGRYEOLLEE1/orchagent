from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START
from langgraph.types import Command

from agent_core.state import BaseAgentState
from agent_core.supervisor import make_supervisor_node
from workflow.teams.research import get_research_graph
from workflow.teams.writing import get_writing_graph
from workflow.teams.vision import get_vision_graph


def get_orchagent_graph(llm_model: str = "gpt-5.4-2026-03-05"):
    # Enable reasoning summary for compatible models (o1, o3, o4-mini, gpt-5.4 etc.)
    llm = ChatOpenAI(
        model_name=llm_model, model_kwargs={"reasoning": {"summary": "auto"}}
    )

    # 1. Subgraphs
    research_graph = get_research_graph(llm)
    writing_graph = get_writing_graph(llm)
    vision_graph = get_vision_graph(llm)

    # 2. Team Wrapper Nodes
    def call_research_team(
        state: BaseAgentState,
    ) -> Command[Literal["head_supervisor"]]:
        # Subgraph invocation
        result = research_graph.invoke({"messages": state["messages"]})
        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=result["messages"][-1].content, name="research_team"
                    )
                ]
            },
            goto="head_supervisor",
        )

    def call_paper_writing_team(
        state: BaseAgentState,
    ) -> Command[Literal["head_supervisor"]]:
        # Subgraph invocation
        result = writing_graph.invoke({"messages": state["messages"]})
        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=result["messages"][-1].content, name="writing_team"
                    )
                ]
            },
            goto="head_supervisor",
        )

    def call_vision_team(state: BaseAgentState) -> Command[Literal["head_supervisor"]]:
        # Subgraph invocation
        result = vision_graph.invoke({"messages": state["messages"]})
        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=result["messages"][-1].content, name="vision_team"
                    )
                ]
            },
            goto="head_supervisor",
        )

    # 3. Head Supervisor
    head_supervisor_node = make_supervisor_node(
        llm, ["research_team", "writing_team", "vision_team"]
    )

    # 4. Build Super Graph
    builder = StateGraph(BaseAgentState)
    builder.add_node("head_supervisor", head_supervisor_node)
    builder.add_node("research_team", call_research_team)
    builder.add_node("writing_team", call_paper_writing_team)
    builder.add_node("vision_team", call_vision_team)

    builder.add_edge(START, "head_supervisor")

    return builder

    return builder
