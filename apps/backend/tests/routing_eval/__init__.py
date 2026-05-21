"""Phase 2.8 — LLM router evaluation harness.

Skeleton landed in this session: dataset format, scorer, and tests against
canned ``RouterDecision`` outputs. Actual LLM execution + nightly job land
together with Phase 2.4 (LLMRouter wire-up).

See ``plans/CODEBASE_WIDE_REFACTORING_PLAN.md`` §4.0.4 for the
contract this harness will eventually enforce (≥ 95% top-1 accuracy,
latency / token-cost budgets, safeguard-firing telemetry).
"""

from tests.routing_eval.scorer import (
    EvalCase,
    EvalReport,
    load_dataset,
    score_decisions,
)

__all__ = ["EvalCase", "EvalReport", "load_dataset", "score_decisions"]
