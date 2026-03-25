from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.timezone import KST
from models.analytics import LLMPricingSnapshot
from services.chat_analytics_service import LLMUsageWriteParams


OPENAI_PRICING_VERSION = "openai-api-pricing-2026-03-25"
OPENAI_PRICING_EFFECTIVE_FROM = datetime(2026, 3, 25, tzinfo=KST)

DEFAULT_OPENAI_PRICING = [
    {
        "provider": "openai",
        "model": "gpt-5.4",
        "input_cost_per_1m_microusd": 2_500_000,
        "output_cost_per_1m_microusd": 15_000_000,
        "cache_read_cost_per_1m_microusd": 250_000,
        "notes": {
            "source": "https://openai.com/api/pricing/",
            "source_date": "2026-03-24",
        },
    },
    {
        "provider": "openai",
        "model": "gpt-5-mini",
        "input_cost_per_1m_microusd": 250_000,
        "output_cost_per_1m_microusd": 2_000_000,
        "cache_read_cost_per_1m_microusd": 25_000,
        "notes": {
            "source": "https://openai.com/api/pricing/",
            "source_date": "2026-03-25",
        },
    },
    {
        "provider": "openai",
        "model": "gpt-5-nano",
        "input_cost_per_1m_microusd": 50_000,
        "output_cost_per_1m_microusd": 400_000,
        "cache_read_cost_per_1m_microusd": 5_000,
        "notes": {
            "source": "https://openai.com/api/pricing/",
            "source_date": "2026-03-25",
        },
    },
]

MODEL_ALIASES = {
    "gpt-5.4-mini": "gpt-5-mini",
    "gpt-5.4-nano": "gpt-5-nano",
}


@dataclass(slots=True)
class CostBreakdown:
    total_cost_microusd: int
    input_cost_microusd: int
    output_cost_microusd: int
    exact_reasoning_cost_microusd: int
    estimated_reasoning_cost_microusd: int
    cost_is_estimated: bool
    reasoning_cost_is_estimated: bool


class LLMPricingService:
    @staticmethod
    def _normalize_model_name(model: str) -> str:
        normalized = MODEL_ALIASES.get(model, model)
        version_suffix = normalized.rsplit("-", 3)
        if (
            len(version_suffix) == 4
            and all(part.isdigit() for part in version_suffix[-3:])
        ):
            return version_suffix[0]
        return normalized

    @staticmethod
    def _microusd_from_token_rate(token_count: int, rate_per_1m: int | None) -> int:
        if not token_count or not rate_per_1m:
            return 0
        return int(round((token_count * rate_per_1m) / 1_000_000))

    @staticmethod
    def _get_default_snapshot_for_model(model: str) -> dict | None:
        normalized_model = LLMPricingService._normalize_model_name(model)
        for snapshot in DEFAULT_OPENAI_PRICING:
            if snapshot["model"] == normalized_model:
                return snapshot
        return None

    @staticmethod
    def calculate_current_cost_breakdown(
        *,
        model: str,
        input_tokens: int,
        cache_read_input_tokens: int,
        output_tokens: int,
        reasoning_output_tokens: int,
    ) -> CostBreakdown:
        snapshot = LLMPricingService._get_default_snapshot_for_model(model)
        if snapshot is None:
            return CostBreakdown(
                total_cost_microusd=0,
                input_cost_microusd=0,
                output_cost_microusd=0,
                exact_reasoning_cost_microusd=0,
                estimated_reasoning_cost_microusd=0,
                cost_is_estimated=True,
                reasoning_cost_is_estimated=True,
            )

        cache_read_tokens = min(cache_read_input_tokens, input_tokens)
        uncached_input_tokens = max(input_tokens - cache_read_tokens, 0)
        input_cost = LLMPricingService._microusd_from_token_rate(
            uncached_input_tokens, snapshot["input_cost_per_1m_microusd"]
        )
        cache_read_cost = LLMPricingService._microusd_from_token_rate(
            cache_read_tokens, snapshot["cache_read_cost_per_1m_microusd"]
        )
        output_cost = LLMPricingService._microusd_from_token_rate(
            output_tokens, snapshot["output_cost_per_1m_microusd"]
        )
        total_cost = input_cost + cache_read_cost + output_cost

        exact_reasoning_cost = 0
        estimated_reasoning_cost = 0
        reasoning_cost_is_estimated = False
        reasoning_rate = snapshot.get("reasoning_cost_per_1m_microusd")
        if reasoning_rate is not None:
            exact_reasoning_cost = LLMPricingService._microusd_from_token_rate(
                reasoning_output_tokens,
                reasoning_rate,
            )
        elif output_tokens > 0 and reasoning_output_tokens > 0:
            estimated_reasoning_cost = int(
                round(output_cost * (reasoning_output_tokens / output_tokens))
            )
            reasoning_cost_is_estimated = True

        return CostBreakdown(
            total_cost_microusd=total_cost,
            input_cost_microusd=input_cost + cache_read_cost,
            output_cost_microusd=output_cost,
            exact_reasoning_cost_microusd=exact_reasoning_cost,
            estimated_reasoning_cost_microusd=estimated_reasoning_cost,
            cost_is_estimated=False,
            reasoning_cost_is_estimated=reasoning_cost_is_estimated,
        )

    @staticmethod
    async def ensure_default_pricing_snapshots(db: AsyncSession) -> None:
        existing = await db.execute(
            select(LLMPricingSnapshot.model, LLMPricingSnapshot.pricing_version).where(
                LLMPricingSnapshot.provider == "openai",
                LLMPricingSnapshot.pricing_version == OPENAI_PRICING_VERSION,
            )
        )
        existing_keys = {(row[0], row[1]) for row in existing.all()}
        to_create = []
        for snapshot in DEFAULT_OPENAI_PRICING:
            key = (snapshot["model"], OPENAI_PRICING_VERSION)
            if key in existing_keys:
                continue
            to_create.append(
                LLMPricingSnapshot(
                    provider=snapshot["provider"],
                    model=snapshot["model"],
                    pricing_version=OPENAI_PRICING_VERSION,
                    effective_from=OPENAI_PRICING_EFFECTIVE_FROM,
                    effective_to=None,
                    input_cost_per_1m_microusd=snapshot["input_cost_per_1m_microusd"],
                    output_cost_per_1m_microusd=snapshot["output_cost_per_1m_microusd"],
                    reasoning_cost_per_1m_microusd=None,
                    cache_read_cost_per_1m_microusd=snapshot["cache_read_cost_per_1m_microusd"],
                    is_estimated=False,
                    notes=snapshot["notes"],
                )
            )

        if to_create:
            db.add_all(to_create)
            await db.commit()

    @staticmethod
    async def resolve_pricing_snapshot(
        db: AsyncSession,
        *,
        provider: str,
        model: str,
        at: datetime,
    ) -> LLMPricingSnapshot | None:
        normalized_model = LLMPricingService._normalize_model_name(model)
        result = await db.execute(
            select(LLMPricingSnapshot)
            .where(
                LLMPricingSnapshot.provider == provider,
                LLMPricingSnapshot.model == normalized_model,
                LLMPricingSnapshot.effective_from <= at,
            )
            .order_by(LLMPricingSnapshot.effective_from.desc())
        )
        snapshots = result.scalars().all()
        for snapshot in snapshots:
            if snapshot.effective_to is None or snapshot.effective_to > at:
                return snapshot
        return None

    @staticmethod
    def apply_snapshot_to_usage(
        params: LLMUsageWriteParams, snapshot: LLMPricingSnapshot | None
    ) -> LLMUsageWriteParams:
        if snapshot is None:
            return params

        cost_breakdown = LLMPricingService.calculate_current_cost_breakdown(
            model=snapshot.model,
            input_tokens=params.input_tokens,
            cache_read_input_tokens=params.cache_read_input_tokens,
            output_tokens=params.output_tokens,
            reasoning_output_tokens=params.reasoning_output_tokens,
        )

        return dataclass_replace(
            params,
            pricing_snapshot_id=snapshot.id,
            input_cost_microusd=cost_breakdown.input_cost_microusd,
            output_cost_microusd=cost_breakdown.output_cost_microusd,
            reasoning_cost_microusd=(
                cost_breakdown.exact_reasoning_cost_microusd or None
            ),
            estimated_reasoning_cost_microusd=cost_breakdown.estimated_reasoning_cost_microusd,
            total_cost_microusd=cost_breakdown.total_cost_microusd,
            cost_is_estimated=cost_breakdown.cost_is_estimated or snapshot.is_estimated,
            reasoning_cost_is_estimated=cost_breakdown.reasoning_cost_is_estimated,
        )
