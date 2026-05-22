import pytest
from unittest.mock import MagicMock

from api.routes.chat import _extract_reasoning_chunk


@pytest.mark.asyncio
async def test_reasoning_extraction_from_additional_kwargs():
    """OpenAI reasoning summary arrives via additional_kwargs.reasoning_summary_text."""
    mock_chunk = MagicMock()
    mock_chunk.additional_kwargs = {
        "reasoning_summary_text": "I am thinking about the number 9.11..."
    }
    mock_chunk.content = ""

    reasoning_chunk = _extract_reasoning_chunk(mock_chunk)
    assert reasoning_chunk == "I am thinking about the number 9.11..."


def test_reasoning_extraction_from_content_items():
    """Reasoning may also appear inline as a content-items dict."""
    mock_chunk = MagicMock()
    mock_chunk.additional_kwargs = {}
    mock_chunk.content = [
        {"type": "reasoning_summary", "summary": "Summarizing the comparison."}
    ]

    assert _extract_reasoning_chunk(mock_chunk) == "Summarizing the comparison."
