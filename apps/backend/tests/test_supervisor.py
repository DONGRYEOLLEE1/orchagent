import pytest
from agent_core.supervisor import make_supervisor_node
from agent_core.state import BaseAgentState
from langchain_core.messages import HumanMessage

class FakeRouterLLM:
    """A Stub LLM that always returns a fixed structured output."""
    def __init__(self, target_node: str):
        self.target_node = target_node
        
    def with_structured_output(self, schema):
        return self
        
    def invoke(self, messages):
        # Stub the Pydantic router response
        return {"next": self.target_node}

def test_supervisor_routes_to_worker():
    """Test if supervisor returns a Command object routing to the requested worker."""
    fake_llm = FakeRouterLLM("search_agent")
    supervisor_func = make_supervisor_node(fake_llm, ["search_agent", "web_scraper"])
    
    state = BaseAgentState(messages=[HumanMessage(content="Find me something")], next="")
    command = supervisor_func(state)
    
    assert command.goto == "search_agent"
    assert command.update["next"] == "search_agent"

def test_supervisor_routes_to_finish():
    """Test if supervisor translates FINISH to the END node (__end__)."""
    fake_llm = FakeRouterLLM("FINISH")
    supervisor_func = make_supervisor_node(fake_llm, ["search_agent", "web_scraper"])
    
    state = BaseAgentState(messages=[HumanMessage(content="All done")], next="")
    command = supervisor_func(state)
    
    assert command.goto == "__end__"
