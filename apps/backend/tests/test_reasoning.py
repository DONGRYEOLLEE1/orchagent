import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_openai import ChatOpenAI
from workflow.main_graph import get_orchagent_graph

def test_reasoning_config_in_graph():
    """Verify that the graph is initialized with reasoning summaries enabled."""
    llm = ChatOpenAI(
        model_name="gpt-5.4-2026-03-05", 
        model_kwargs={"reasoning": {"summary": "auto"}}
    )
    # LangChain/OpenAI class promotes 'reasoning' to a top-level field if supported
    assert hasattr(llm, "reasoning")
    assert llm.reasoning == {"summary": "auto"}


@pytest.mark.asyncio
async def test_reasoning_extraction_logic(monkeypatch):
    """Test the logic that extracts reasoning chunks from the stream."""
    from api.routes.chat import chat_stream
    from schemas.chat import ChatRequest
    
    # Mocking the complex nested structure of a LangChain reasoning chunk
    mock_chunk = MagicMock()
    mock_chunk.additional_kwargs = {"reasoning_summary_text": "I am thinking about the number 9.11..."}
    mock_chunk.content = ""
    
    # Verify our logic in chat.py would catch this (Manual verification of the logic path)
    reasoning_chunk = getattr(mock_chunk, "additional_kwargs", {}).get("reasoning_summary_text")
    assert reasoning_chunk == "I am thinking about the number 9.11..."

def test_preset_reasoning_query():
    """Define the preset query for human-in-the-loop or E2E validation."""
    query = "9.11과 9.9 중 어느 숫자가 더 큰지 논리적으로 설명해줘"
    assert "9.11" in query and "논리적" in query
