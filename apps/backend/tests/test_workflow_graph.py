import pytest
from workflow.main_graph import get_orchagent_graph

def test_graph_compilation_success():
    """
    Test that the main orchestration graph and all subgraphs compile 
    without cyclic or undefined node errors.
    
    Graph compilation parses the schema without making actual LLM API calls.
    """
    builder = get_orchagent_graph(llm_model="gpt-5.4-2026-03-05")
    graph = builder.compile()
    
    # Verify core nodes exist
    assert "head_supervisor" in graph.nodes
    assert "research_team" in graph.nodes
    assert "writing_team" in graph.nodes
    
    # A compiled graph should have a valid structure
    assert graph is not None
