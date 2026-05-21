"""Score predicted RouterDecisions against the golden dataset.

Phase 2.8 — pure-function scoring layer so the actual LLM execution
script (lands with Phase 2.4 LLMRouter) only has to plug in
``decide(case) -> RouterDecision`` and call :func:`score_decisions`.

No LLM calls happen here, so this module is cheap to unit-test and safe
to import from anywhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from agent_core.router_schema import RouterDecision


GOLDEN_DATASET_PATH = Path(__file__).resolve().parent / "golden_dataset.json"


@dataclass(slots=True)
class EvalCase:
    """One row of the golden dataset."""

    id: str
    category: str
    user_message: str
    repo_bound: bool
    expected_next: str
    expected_request_review: bool
    rationale: str

    @classmethod
    def from_raw(cls, raw: dict) -> "EvalCase":
        return cls(
            id=raw["id"],
            category=raw["category"],
            user_message=raw["user_message"],
            repo_bound=bool(raw.get("repo_bound", False)),
            expected_next=raw["expected_next"],
            expected_request_review=bool(raw.get("expected_request_review", False)),
            rationale=raw.get("rationale", ""),
        )


@dataclass(slots=True)
class EvalReport:
    """Aggregate measurements of one harness run."""

    total: int = 0
    top1_hits: int = 0
    review_matches: int = 0
    category_hits: dict[str, int] = field(default_factory=dict)
    category_totals: dict[str, int] = field(default_factory=dict)
    failures: list[dict] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.top1_hits / self.total if self.total else 0.0

    @property
    def review_accuracy(self) -> float:
        return self.review_matches / self.total if self.total else 0.0

    def category_accuracy(self, category: str) -> float:
        total = self.category_totals.get(category, 0)
        return (self.category_hits.get(category, 0) / total) if total else 0.0


def load_dataset(path: Path | None = None) -> list[EvalCase]:
    """Load the golden dataset from disk."""
    raw = json.loads((path or GOLDEN_DATASET_PATH).read_text(encoding="utf-8"))
    return [EvalCase.from_raw(item) for item in raw["cases"]]


def score_decisions(
    pairs: Iterable[tuple[EvalCase, RouterDecision]],
) -> EvalReport:
    """Compare ``(case, predicted_decision)`` pairs and aggregate accuracy."""
    report = EvalReport()
    for case, decision in pairs:
        report.total += 1
        report.category_totals[case.category] = (
            report.category_totals.get(case.category, 0) + 1
        )

        next_hit = decision.next == case.expected_next
        review_hit = decision.request_review == case.expected_request_review

        if next_hit:
            report.top1_hits += 1
            report.category_hits[case.category] = (
                report.category_hits.get(case.category, 0) + 1
            )
        if review_hit:
            report.review_matches += 1

        if not (next_hit and review_hit):
            report.failures.append(
                {
                    "case_id": case.id,
                    "expected_next": case.expected_next,
                    "got_next": decision.next,
                    "expected_request_review": case.expected_request_review,
                    "got_request_review": decision.request_review,
                    "reason": decision.reason,
                }
            )
    return report


__all__ = [
    "EvalCase",
    "EvalReport",
    "GOLDEN_DATASET_PATH",
    "load_dataset",
    "score_decisions",
]
