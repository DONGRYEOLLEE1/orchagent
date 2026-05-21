"""Head-supervisor task-plan progression regression placeholder.

The plan-driven override that read ``task_plan`` and forced the head
supervisor onto the next pending stage was removed in Phase 2.3 round 2.
The original test (``test_head_supervisor_treats_duplicate_completed_team_entries_as_complete``)
asserted that override behaviour and no longer reflects the LLM-driven
routing policy (plan §4.0): when the plan is satisfied, it is the LLM —
not the supervisor — that picks FINISH, and the
``head_team_redirect_limit`` safeguard remains as the loop-breaker.

LLM-driven plan completion behaviour is covered by the routing evaluation
harness (Phase 2.8); the redirect-limit safeguard itself is covered by
``test_router_safeguards.py``.
"""
