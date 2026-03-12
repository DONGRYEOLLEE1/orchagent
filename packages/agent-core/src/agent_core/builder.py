from abc import ABC, abstractmethod
from typing import List, Any

from langgraph.graph import StateGraph, START
from langgraph.prebuilt import create_react_agent
from langchain_core.language_models.chat_models import BaseChatModel

from agent_core.state import BaseAgentState
from agent_core.supervisor import make_supervisor_node
from agent_core.validator import make_validator_node


class TeamBuilder(ABC):
    """
    Abstract class to build a team subgraph.
    Encapsulates the creation of nodes, edges, and the supervisor.
    """

    def __init__(self, llm: BaseChatModel, team_name: str, members: List[str]):
        self.llm = llm
        self.team_name = team_name
        self.members = members
        self.builder = StateGraph(BaseAgentState)  # type: ignore

    @abstractmethod
    def register_nodes(self):
        """Register worker nodes to the graph."""
        pass

    def add_worker(self, node_name: str, *, tools: List[Any], prompt: str):
        """Register a worker as a native LangGraph subgraph instead of a blocking wrapper."""
        worker_graph = create_react_agent(
            model=self.llm,
            tools=tools,
            prompt=prompt,
            state_schema=BaseAgentState,
            version="v2",
            name=node_name,
        )
        self.builder.add_node(node_name, worker_graph)

    def build(self, with_validator: bool = False):
        """Compiles the subgraph with a supervisor."""
        # 1. Register Supervisor
        supervisor_node = make_supervisor_node(
            self.llm,
            self.members,
            layer="team",
            team_name=self.team_name,
        )
        self.builder.add_node("supervisor", supervisor_node)

        if with_validator:
            validator_node = make_validator_node(self.llm, self.team_name)
            self.builder.add_node("validator", validator_node)

        # 2. Register Workers (Implemented by subclasses)
        self.register_nodes()

        # 3. Set entry point
        self.builder.add_edge(START, "supervisor")

        # 4. Worker subgraphs return to the validator or team supervisor after completion
        return_node = "validator" if with_validator else "supervisor"
        for member in self.members:
            self.builder.add_edge(member, return_node)

        return self.builder.compile()
