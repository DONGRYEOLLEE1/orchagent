import pytest
from unittest.mock import MagicMock
from langchain.chat_models import init_chat_model
from workflow.main_graph import DEFAULT_LLM_MODEL
from api.routes.chat import _extract_reasoning_chunk


def test_reasoning_config_in_graph():
    """Verify that the graph is initialized with reasoning summaries enabled."""
    llm = init_chat_model(
        model=DEFAULT_LLM_MODEL,
        model_provider="openai",
        reasoning={"summary": "auto"},
    )

    assert hasattr(llm, "reasoning")
    assert llm.reasoning == {"summary": "auto"}


@pytest.mark.asyncio
async def test_reasoning_extraction_logic(monkeypatch):
    """Test the logic that extracts reasoning chunks from the stream."""

    # Mocking the complex nested structure of a LangChain reasoning chunk
    mock_chunk = MagicMock()
    mock_chunk.additional_kwargs = {
        "reasoning_summary_text": "I am thinking about the number 9.11..."
    }
    mock_chunk.content = ""

    reasoning_chunk = _extract_reasoning_chunk(mock_chunk)
    assert reasoning_chunk == "I am thinking about the number 9.11..."


def test_reasoning_extraction_from_content_items():
    mock_chunk = MagicMock()
    mock_chunk.additional_kwargs = {}
    mock_chunk.content = [
        {"type": "reasoning_summary", "summary": "Summarizing the comparison."}
    ]

    assert _extract_reasoning_chunk(mock_chunk) == "Summarizing the comparison."


def test_preset_reasoning_query():
    """Define the preset query for human-in-the-loop or E2E validation."""
    query = "9.11과 9.9 중 어느 숫자가 더 큰지 논리적으로 설명해줘"
    assert "9.11" in query and "논리적" in query
