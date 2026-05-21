"""Backwards-compatible adapter around the head/team supervisor factories.

Phase 2.4 of the codebase-wide refactor moved the actual routing logic
into :mod:`agent_core.supervisors` (split per layer + shared LLM router).
Existing callers (``main_graph.py``, ``builder.TeamBuilder``, and a
substantial unit-test surface) still import ``make_supervisor_node`` from
this module, so we keep the wrapper here. The wrapper does nothing more
than dispatch to the right factory based on ``layer``.

Per the head/team responsibilities split:

- ``layer="head"`` → :func:`agent_core.supervisors.make_head_supervisor_node`
- ``layer="team"`` → :func:`agent_core.supervisors.make_team_supervisor_node`

The historical helpers (``_extract_message_text``,
``_latest_user_request_text``, ``_orchagent_identity_response``) now live
inside ``agent_core.supervisors.head_supervisor`` where they are actually
used. They are re-exported here only for any external test that imported
them directly.
"""

from __future__ import annotations

from typing import Callable, Literal

from langchain_core.language_models.chat_models import BaseChatModel

from agent_core.supervisors.head_supervisor import (
    _extract_message_text,
    _latest_user_request_text,
    _orchagent_identity_response,
    make_head_supervisor_node,
)
from agent_core.supervisors.team_supervisor import make_team_supervisor_node


def make_supervisor_node(
    llm: BaseChatModel,
    members: list[str],
    system_prompt_template: str | None = None,
    *,
    layer: Literal["head", "team"] = "head",
    team_name: str | None = None,
    final_node_name: str | None = None,
    max_team_dispatches: int | None = None,
) -> Callable:
    """Dispatch to the head or team supervisor factory.

    Preserves the legacy positional signature
    ``(llm, members, system_prompt_template, *, layer, ...)``
    so existing call sites do not change.
    """
    if layer == "head":
        return make_head_supervisor_node(
            llm,
            members,
            system_prompt_template=system_prompt_template,
            final_node_name=final_node_name,
            max_team_dispatches=max_team_dispatches,
        )
    return make_team_supervisor_node(
        llm,
        members,
        system_prompt_template=system_prompt_template,
        team_name=team_name,
        max_team_dispatches=max_team_dispatches,
    )


__all__ = [
    "_extract_message_text",
    "_latest_user_request_text",
    "_orchagent_identity_response",
    "make_supervisor_node",
]
