"""Head + team supervisor node factories.

Phase 2.4 split the previous monolithic ``agent_core.supervisor`` module
into one factory per layer (head vs team) plus a shared LLM router. The
public surface here is intentionally tiny so call sites can do:

    from agent_core.supervisors import (
        make_head_supervisor_node,
        make_team_supervisor_node,
    )
"""

from agent_core.supervisors.head_supervisor import make_head_supervisor_node
from agent_core.supervisors.team_supervisor import make_team_supervisor_node
from agent_core.supervisors.llm_router import compose_system_prompt, decide_route

__all__ = [
    "compose_system_prompt",
    "decide_route",
    "make_head_supervisor_node",
    "make_team_supervisor_node",
]
