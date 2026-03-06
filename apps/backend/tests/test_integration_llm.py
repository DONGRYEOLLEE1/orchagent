import pytest
import os
from workflow.main_graph import get_orchagent_graph

# Marked as an integration test so it can be skipped in standard CI runs
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "mock-key", 
    reason="Requires a valid OPENAI_API_KEY to test real LLM connectivity."
)
def test_real_llm_routing_instantiation():
    """
    Ensures that the application can instantiate and bind tools using a REAL LLM key.
    This protects against underlying library deprecations (e.g., LangChain updates).
    """
    try:
        builder = get_orchagent_graph()
        graph = builder.compile()
        assert graph is not None
    except Exception as e:
        pytest.fail(f"Integration with real LLM failed: {e}")
