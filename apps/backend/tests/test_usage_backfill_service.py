from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from models.analytics import LLMUsageEvent
from services.usage_backfill_service import UsageBackfillService


def test_load_usage_log_entries_filters_user_and_before(tmp_path: Path):
    log_path = tmp_path / "usage.jsonl"
    log_path.write_text(
        "\n".join(
            [
                '{"user_id":"user-1","model":"gpt-5.4-mini","prompt_tokens":1,"completion_tokens":2,"total_tokens":3,"timestamp":"2026-03-24T11:00:00+09:00"}',
                '{"user_id":"user-1","model":"gpt-5.4-mini","prompt_tokens":2,"completion_tokens":4,"total_tokens":6,"timestamp":"2026-03-25T11:00:00+09:00"}',
                '{"user_id":"user-2","model":"gpt-5.4-mini","prompt_tokens":9,"completion_tokens":9,"total_tokens":18,"timestamp":"2026-03-24T11:00:00+09:00"}',
            ]
        ),
        encoding="utf-8",
    )

    entries = UsageBackfillService.load_usage_log_entries(
        log_path=log_path,
        user_id="user-1",
        before=datetime.fromisoformat("2026-03-25T00:00:00+09:00"),
    )

    assert len(entries) == 1
    assert entries[0].total_tokens == 3
    assert entries[0].timestamp.isoformat().startswith("2026-03-24T11:00:00")


@pytest.mark.asyncio
async def test_get_first_exact_usage_at_returns_oldest_event():
    oldest = LLMUsageEvent(id=uuid4(), created_at=datetime.fromisoformat("2026-03-25T05:00:00+09:00"))
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = oldest
    mock_db.execute.return_value = mock_result

    resolved = await UsageBackfillService.get_first_exact_usage_at(
        mock_db, user_id="user-1"
    )

    assert resolved == oldest.created_at
