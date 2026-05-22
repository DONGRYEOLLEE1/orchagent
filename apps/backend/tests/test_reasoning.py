import pytest
from unittest.mock import MagicMock

from api.routes.chat import _extract_reasoning_chunk


@pytest.mark.parametrize(
    "additional_kwargs,content,expected",
    [
        # OpenAI reasoning summary arrives via additional_kwargs.
        (
            {"reasoning_summary_text": "I am thinking about the number 9.11..."},
            "",
            "I am thinking about the number 9.11...",
        ),
        # Reasoning may also appear inline as a content-items dict.
        (
            {},
            [{"type": "reasoning_summary", "summary": "Summarizing the comparison."}],
            "Summarizing the comparison.",
        ),
    ],
    ids=["additional_kwargs", "content_items"],
)
def test_reasoning_extraction_handles_both_shapes(additional_kwargs, content, expected):
    """Both OpenAI reasoning carrier shapes (additional_kwargs and inline content) extract."""
    mock_chunk = MagicMock()
    mock_chunk.additional_kwargs = additional_kwargs
    mock_chunk.content = content

    assert _extract_reasoning_chunk(mock_chunk) == expected
