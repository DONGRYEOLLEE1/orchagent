from abc import ABC, abstractmethod
from typing import List, Callable, Any
from langgraph.graph import StateGraph, START
from langchain_core.language_models.chat_models import BaseChatModel
from agent_core.state import BaseAgentState
from agent_core.supervisor import make_supervisor_node

class TeamBuilder(ABC):
    """
    Abstract class to build a team subgraph.
    Encapsulates the creation of nodes, edges, and the supervisor.
    """
    def __init__(self, llm: BaseChatModel, team_name: str, members: List[str]):
        self.llm = llm
        self.team_name = team_name
        self.members = members
        self.builder = StateGraph(BaseAgentState)

    @abstractmethod
    def register_nodes(self):
        """Register worker nodes to the graph."""
        pass

    def build(self):
        """Compiles the subgraph with a supervisor."""
        # 1. Register Supervisor
        supervisor_node = make_supervisor_node(self.llm, self.members)
        self.builder.add_node("supervisor", supervisor_node)
        
        # 2. Register Workers (Implemented by subclasses)
        self.register_nodes()
        
        # 3. Set entry point
        self.builder.add_edge(START, "supervisor")
        
        return self.builder.compile()
