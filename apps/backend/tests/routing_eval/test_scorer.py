"""Unit tests for the routing-eval scoring layer.

These tests run on canned RouterDecision objects so they're cheap and
deterministic — no LLM is called. The real LLM-driven harness lands
together with Phase 2.4 LLMRouter wire-up.
"""

from __future__ import annotations

from agent_core.router_schema import RouterDecision

from tests.routing_eval.scorer import (
    EvalCase,
    GOLDEN_DATASET_PATH,
    load_dataset,
    score_decisions,
)


def _make_case(**overrides):
    base = dict(
        id="t-1",
        category="research",
        user_message="hello",
        repo_bound=False,
        expected_next="research_team",
        expected_request_review=False,
        rationale="",
    )
    base.update(overrides)
    return EvalCase(**base)


def test_golden_dataset_loads_and_has_minimum_coverage():
    cases = load_dataset()
    assert GOLDEN_DATASET_PATH.exists()
    # ≥ 8 cases until the dataset reaches the 50-case target in 2.4
    assert len(cases) >= 8
    categories = {case.category for case in cases}
    expected_minimum = {
        "coding",
        "coding-no-repo",
        "research",
        "data_science",
        "vision",
        "writing",
        "FINISH",
        "approval_request",
    }
    assert expected_minimum.issubset(categories)


def test_score_decisions_counts_perfect_run():
    cases = [
        _make_case(id="a", expected_next="research_team"),
        _make_case(id="b", expected_next="coding_team", category="coding"),
    ]
    pairs = [
        (cases[0], RouterDecision(next="research_team", reason="ok")),
        (cases[1], RouterDecision(next="coding_team", reason="ok")),
    ]
    report = score_decisions(pairs)
    assert report.total == 2
    assert report.top1_hits == 2
    assert report.accuracy == 1.0
    assert report.failures == []


def test_score_decisions_records_top1_miss():
    case = _make_case(expected_next="research_team")
    decision = RouterDecision(next="FINISH", reason="thought it was a greeting")
    report = score_decisions([(case, decision)])
    assert report.total == 1
    assert report.top1_hits == 0
    assert report.accuracy == 0.0
    assert len(report.failures) == 1
    failure = report.failures[0]
    assert failure["expected_next"] == "research_team"
    assert failure["got_next"] == "FINISH"


def test_score_decisions_tracks_request_review_separately():
    case = _make_case(
        expected_next="coding_team",
        expected_request_review=True,
        category="coding",
    )
    decision = RouterDecision(
        next="coding_team", reason="ok", request_review=False
    )
    report = score_decisions([(case, decision)])
    assert report.top1_hits == 1  # next matches
    assert report.review_matches == 0  # but review flag missed
    assert report.review_accuracy == 0.0
    assert len(report.failures) == 1  # any mismatch lands in failures


def test_score_decisions_category_accuracy():
    cases = [
        _make_case(id="r1", category="research", expected_next="research_team"),
        _make_case(id="r2", category="research", expected_next="research_team"),
        _make_case(id="c1", category="coding", expected_next="coding_team"),
    ]
    decisions = [
        RouterDecision(next="research_team"),
        RouterDecision(next="FINISH"),  # miss
        RouterDecision(next="coding_team"),
    ]
    report = score_decisions(list(zip(cases, decisions)))
    assert report.category_accuracy("research") == 0.5
    assert report.category_accuracy("coding") == 1.0
    assert report.category_accuracy("vision") == 0.0  # absent category


def test_dataset_cases_all_have_required_fields():
    cases = load_dataset()
    for case in cases:
        assert case.id and isinstance(case.id, str)
        assert case.user_message and isinstance(case.user_message, str)
        assert case.expected_next in {
            "FINISH",
            "research_team",
            "coding_team",
            "data_science_team",
            "vision_team",
            "writing_team",
        }
