import pytest
from unittest.mock import AsyncMock, MagicMock
from services.trace_service import TraceService


@pytest.mark.asyncio
async def test_create_event():
    """Test if TraceService correctly creates and persists an event using a Mock DB session."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()  # .add is synchronous in SQLAlchemy
    mock_db.add_all = MagicMock()

    event = await TraceService.create_event(
        db=mock_db,
        thread_id="test_thread",
        event_type="on_node_start",
        node_name="research_team",
        payload={"dummy": "data"},
    )

    assert event.thread_id == "test_thread"
    assert event.node_name == "research_team"

    # Verify DB interaction
    mock_db.add_all.assert_called_once_with([event])
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_events_batches_single_commit():
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
async def test_get_thread_traces():
    """Test retrieving traces for a specific thread."""
    mock_db = AsyncMock()

    # Mocking the nested sqlalchemy result structure (result.scalars().all() is synchronous)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["trace1", "trace2"]
    mock_db.execute.return_value = mock_result

    traces = await TraceService.get_thread_traces(mock_db, "test_thread")

    assert len(traces) == 2
    mock_db.execute.assert_awaited_once()


def test_trace_payload_optimization():
    """Large base64 strings and verbose payload strings should be truncated."""
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
