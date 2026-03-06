from langgraph.graph import MessagesState

class BaseAgentState(MessagesState):
    next: str
