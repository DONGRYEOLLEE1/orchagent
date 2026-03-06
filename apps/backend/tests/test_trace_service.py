import pytest
from unittest.mock import AsyncMock, MagicMock
from services.trace_service import TraceService

@pytest.mark.asyncio
async def test_create_event():
    """Test if TraceService correctly creates and persists an event using a Mock DB session."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock() # .add is synchronous in SQLAlchemy
    
    event = await TraceService.create_event(
        db=mock_db,
        thread_id="test_thread",
        event_type="on_node_start",
        node_name="research_team",
        payload={"dummy": "data"}
    )
    
    assert event.thread_id == "test_thread"
    assert event.node_name == "research_team"
    
    # Verify DB interaction
    mock_db.add.assert_called_once_with(event)
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
