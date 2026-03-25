from datetime import UTC, datetime
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from models.analytics import LLMPricingSnapshot
from services.chat_analytics_service import LLMUsageWriteParams
from services.llm_pricing_service import LLMPricingService


def test_apply_snapshot_to_usage_calculates_exact_total_and_estimated_reasoning_cost():
    snapshot = LLMPricingSnapshot(
        id=uuid4(),
        provider="openai",
        model="gpt-5.4-mini",
        pricing_version="test",
        effective_from=datetime(2026, 3, 24, tzinfo=UTC),
        input_cost_per_1m_microusd=250_000,
        output_cost_per_1m_microusd=2_000_000,
        reasoning_cost_per_1m_microusd=None,
        cache_read_cost_per_1m_microusd=25_000,
        is_estimated=False,
    )
    params = LLMUsageWriteParams(
        user_id="user-1",
        thread_id="thread-1",
        turn_id=uuid4(),
        run_id="run-1",
        trace_id="trace-1",
        span_id="run-1",
        parent_span_id=None,
        node_name="finalizer",
        provider="openai",
        model="gpt-5.4-mini",
        request_role="finalizer",
        input_tokens=1000,
        output_tokens=2000,
        total_tokens=3000,
        cache_read_input_tokens=200,
        cache_write_input_tokens=0,
        reasoning_output_tokens=500,
        text_output_tokens=1500,
        usage_metadata={},
        created_at=datetime(2026, 3, 24, tzinfo=UTC),
    )

    priced = LLMPricingService.apply_snapshot_to_usage(params, snapshot)

    assert priced.input_cost_microusd == 205
    assert priced.output_cost_microusd == 4000
    assert priced.total_cost_microusd == 4205
    assert priced.reasoning_cost_microusd is None
    assert priced.estimated_reasoning_cost_microusd == 1000
    assert priced.reasoning_cost_is_estimated is True


@pytest.mark.asyncio
async def test_resolve_pricing_snapshot_normalizes_model_alias():
    snapshot = LLMPricingSnapshot(
        id=uuid4(),
        provider="openai",
        model="gpt-5-nano",
        pricing_version="test",
        effective_from=datetime(2026, 3, 24, tzinfo=UTC),
        input_cost_per_1m_microusd=50_000,
        output_cost_per_1m_microusd=400_000,
        reasoning_cost_per_1m_microusd=None,
        cache_read_cost_per_1m_microusd=5_000,
        is_estimated=False,
    )
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [snapshot]
    mock_db.execute.return_value = mock_result

    resolved = await LLMPricingService.resolve_pricing_snapshot(
        mock_db,
        provider="openai",
        model="gpt-5-nano",
        at=datetime(2026, 3, 24, tzinfo=UTC),
    )

    assert resolved is snapshot
