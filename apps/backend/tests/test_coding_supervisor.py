"""Coding-team supervisor regression tests.

The team-forced-order machine that used to live in ``supervisor.py`` was
removed in Phase 2.3 round 2 — the coding team now relies on the LLM router
plus the cross-graph safeguards (``allowed_next_nodes`` coercion,
``max_team_dispatches``, ``head_team_redirect_limit``, and the
coding_team-without-repo-binding final guard tested in ``test_supervisor.py``).

The forced-order test cases that previously lived here
(``test_coding_team_supervisor_starts_with_codebase_explorer`` and
``test_coding_team_supervisor_routes_to_runtime_verifier_when_requested``)
have been deleted along with the heuristics they validated. LLM-driven
coding-team routing is covered by the routing evaluation harness (Phase 2.8)
and by the safeguards' own unit tests (``test_router_safeguards.py``).
"""
