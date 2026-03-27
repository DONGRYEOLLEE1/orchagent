from workflow.main_graph import DEFAULT_LLM_MODEL, get_orchagent_graph


def test_graph_compilation_success():
    """
    Test that the main orchestration graph and all subgraphs compile
    without cyclic or undefined node errors.

    Graph compilation parses the schema without making actual LLM API calls.
    """
    builder = get_orchagent_graph(llm_model=DEFAULT_LLM_MODEL)
    graph = builder.compile()

    # Verify core nodes exist
    assert "head_supervisor" in graph.nodes
    assert "research_team" in graph.nodes
    assert "writing_team" in graph.nodes
    assert "vision_team" in graph.nodes
    assert "data_science_team" in graph.nodes

    # A compiled graph should have a valid structure
    assert graph is not None
