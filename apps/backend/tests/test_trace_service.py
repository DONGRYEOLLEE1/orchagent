import pytest
from unittest.mock import AsyncMock, MagicMock
from services.trace_service import TraceService


@pytest.mark.asyncio
async def test_create_events_batches_single_commit():
    """TraceService.create_events must persist all events with a single commit."""
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()

    events = [
        TraceService.build_event(
            thread_id="thread",
            event_type="status",
            node_name="head_supervisor",
            payload={"event_type": "status", "status": "running"},
        ),
        TraceService.build_event(
            thread_id="thread",
            event_type="checkpoint",
            node_name="checkpoint",
            payload={"event_type": "checkpoint", "checkpoint_id": "cp-1"},
        ),
    ]

    saved = await TraceService.create_events(mock_db, events)

    assert saved == events
    mock_db.add_all.assert_called_once_with(events)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_thread_traces_returns_persisted_rows():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["trace1", "trace2"]
    mock_db.execute.return_value = mock_result

    traces = await TraceService.get_thread_traces(mock_db, "test_thread")

    assert len(traces) == 2


def test_trace_payload_optimization():
    """Large base64 strings and verbose payload strings must be truncated."""
    long_base64 = "data:image/jpeg;base64," + "A" * 1000
    long_output = "B" * 5000
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "image_url", "image_url": {"url": long_base64}},
                ],
            }
        ],
        "output": long_output,
    }

    optimized = TraceService._optimize_payload(payload)

    img_url = optimized["messages"][0]["content"][1]["image_url"]["url"]
    assert len(img_url) < 200
    assert "[BASE64 TRUNCATED]" in img_url
    assert optimized["output"].endswith("[TRUNCATED]")
