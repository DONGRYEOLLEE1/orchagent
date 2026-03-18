from abc import ABC, abstractmethod
from typing import List, Any

from langgraph.graph import StateGraph, START
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel

from agent_core.state import BaseAgentState
from agent_core.supervisor import make_supervisor_node
from agent_core.validator import make_reviewer_node


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
        """Register a worker as a native LangGraph subgraph.

        Dynamic tool filtering is intentionally disabled for now because the
        current `langchain.agents.create_agent()` API expects a concrete
        `BaseChatModel`, not the callable model factory pattern used by older
        experiments. Tool policy can be reintroduced later via middleware.
        """

        worker_graph = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=prompt,
            state_schema=BaseAgentState,  # type: ignore
            name=node_name,
        )
        self.builder.add_node(node_name, worker_graph)

    def build(
        self, with_validator: bool = False, max_team_dispatches: int | None = None
    ):
        """Compiles the subgraph with a supervisor."""
        # 1. Register Supervisor
        supervisor_node = make_supervisor_node(
            self.llm,
            self.members,
            layer="team",
            team_name=self.team_name,
            max_team_dispatches=max_team_dispatches,
        )
        self.builder.add_node("supervisor", supervisor_node)

        if with_validator:
            reviewer_node = make_reviewer_node(self.llm, self.team_name)
            self.builder.add_node("reviewer", reviewer_node)

        # 2. Register Workers (Implemented by subclasses)
        self.register_nodes()

        # 3. Set entry point
        self.builder.add_edge(START, "supervisor")

        # 4. Worker subgraphs return to the reviewer or team supervisor after completion
        return_node = "reviewer" if with_validator else "supervisor"
        for member in self.members:
            self.builder.add_edge(member, return_node)

        return self.builder.compile()
