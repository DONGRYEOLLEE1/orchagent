from unittest.mock import AsyncMock

import pytest

from services.thread_telemetry_service import ThreadTelemetryService


@pytest.mark.asyncio
async def test_get_thread_telemetry_reads_latest_reasoning_and_suggestions(monkeypatch):
    db = AsyncMock()

    async def mock_get_latest_trace_payload(db, thread_id, event_type):
        if event_type == "reasoning_summary":
            return {"content": "요약된 reasoning"}
        if event_type == "suggested_queries_summary":
            return {
                "suggested_queries": [
                    "후속 질문 1",
                    "후속 질문 2",
                    "후속 질문 1",
                ]
            }
        return None

    monkeypatch.setattr(
        ThreadTelemetryService,
        "_get_latest_trace_payload",
        mock_get_latest_trace_payload,
    )

    telemetry = await ThreadTelemetryService.get_thread_telemetry(db, "thread-1")

    assert telemetry.reasoning_summary == "요약된 reasoning"
    assert telemetry.suggested_queries == ["후속 질문 1", "후속 질문 2"]
