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


def test_data_science_cases_all_route_to_data_science_team():
    """첫 분기 보장 — 데이터 첨부 케이스는 반드시 data_science_team으로.

    plan §"data_engineer 첫 분기 보장" — CLAUDE.md의 도메인별 첫 분기
    매핑 표를 코드로 강제. data_science 카테고리 케이스가 다른 팀으로
    fan-out되기 시작하면 LLM 프롬프트(SYSTEM_SUPERVISOR_PROMPT
    `# TEAM SELECTION HINTS`)가 약화된 것이므로 즉시 잡는다.
    """
    cases = load_dataset()
    data_science_cases = [c for c in cases if c.category == "data_science"]
    assert len(data_science_cases) >= 5, (
        "data_science 카테고리 케이스가 부족합니다 — "
        "데이터 첨부 첫 분기 회귀 차단선이 약해집니다."
    )
    for case in data_science_cases:
        assert case.expected_next == "data_science_team", (
            f"{case.id}: data_science 케이스가 {case.expected_next}로 라우팅됨 "
            f"— CLAUDE.md §'도메인별 첫 분기 의무' 위반"
        )
        assert case.expected_request_review is False, (
            f"{case.id}: data_science 케이스는 python_repl 샌드박스라서 "
            "request_review=False 여야 합니다 (인간 승인 불필요)."
        )
