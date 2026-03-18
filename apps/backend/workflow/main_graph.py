from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START

from agent_core.state import BaseAgentState
from agent_core.supervisor import make_supervisor_node
from agent_core.nodes.finalizer import make_finalizer_node
from agent_core.nodes.planner import make_planner_node
from workflow.teams.research import get_research_graph
from workflow.teams.writing import get_writing_graph
from workflow.teams.vision import get_vision_graph
from core.config import settings


def get_orchagent_graph(llm_model: str = "gpt-5.4-2026-03-05"):
    # Enable reasoning summary for compatible models (o1, o3, o4-mini, gpt-5.4 etc.)
    llm = ChatOpenAI(
        model_name=llm_model, model_kwargs={"reasoning": {"summary": "auto"}}
    )

    # 1. Subgraphs
    research_graph = get_research_graph(llm)
    writing_graph = get_writing_graph(llm)
    vision_graph = get_vision_graph(llm)

    # 2. Nodes
    planner_node = make_planner_node(llm)
    finalizer_node = make_finalizer_node(llm)
    head_supervisor_node = make_supervisor_node(
        llm,
        ["research_team", "writing_team", "vision_team"],
        layer="head",
        final_node_name="finalizer",
        max_team_dispatches=max(
            settings.RESEARCH_TEAM_MAX_DISPATCHES,
            settings.WRITING_TEAM_MAX_DISPATCHES,
        ),
    )

    # 3. Build Super Graph
    builder = StateGraph(BaseAgentState)  # type: ignore
    builder.add_node("planner", planner_node)
    builder.add_node("head_supervisor", head_supervisor_node)
    builder.add_node("finalizer", finalizer_node)

    # Add native subgraphs directly as nodes
    builder.add_node("research_team", research_graph)
    builder.add_node("writing_team", writing_graph)
    builder.add_node("vision_team", vision_graph)

    # 4. Set Edges
    builder.add_edge(START, "planner")
    # Planner dynamically routes to head_supervisor via Command

    # Route back to head supervisor after subgraphs complete (Native subgraph routing)
    builder.add_edge("research_team", "head_supervisor")
    builder.add_edge("writing_team", "head_supervisor")
    builder.add_edge("vision_team", "head_supervisor")

    return builder
