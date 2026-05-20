"""Encapsulate the chat route's dependency on agent_core / workflow / agent_tools.

Phase 1.5 of the codebase-wide refactor. AGENTS.md forbids the router layer
from importing the orchestration packages directly. This service is the single
seam that the chat route uses to:

- compile the orchagent graph (``OrchestrationService.get_graph``)
- look up the default LLM model id (``OrchestrationService.DEFAULT_LLM_MODEL``)
- ask whether a piece of user text should force the coding team or trigger a
  human-approval interrupt (``requires_coding_team`` / ``requires_human_approval``)
- bind / read / clear the per-turn tool runtime context

Phase 2 will swap the rule-based ``requires_*`` helpers for LLM-driven router
decisions; the chat route should keep calling these wrappers so the swap
happens entirely inside ``OrchestrationService`` without touching the router.

``ToolAttachment`` and ``ToolRuntimeContext`` are re-exported so the router can
keep its existing type annotations without importing ``agent_tools.runtime``.
"""

from __future__ import annotations

from typing import Any

from agent_core.supervisor import (
    requires_coding_team_for_text as _requires_coding_team_for_text,
    requires_human_approval_for_text as _requires_human_approval_for_text,
)
from agent_tools.runtime import (
    ToolAttachment as ToolAttachment,
    ToolRuntimeContext as ToolRuntimeContext,
    collect_runtime_artifacts as _collect_runtime_artifacts,
    get_tool_runtime_context as _get_tool_runtime_context,
    reset_tool_runtime_context as _reset_tool_runtime_context,
    set_tool_runtime_context as _set_tool_runtime_context,
)
from workflow.main_graph import (
    DEFAULT_LLM_MODEL as DEFAULT_LLM_MODEL,
    get_orchagent_graph as _get_orchagent_graph,
)


__all__ = [
    "DEFAULT_LLM_MODEL",
    "OrchestrationService",
    "ToolAttachment",
    "ToolRuntimeContext",
]


class OrchestrationService:
    """Single seam between the FastAPI router and orchestration packages."""

    DEFAULT_LLM_MODEL: str = DEFAULT_LLM_MODEL

    @staticmethod
    def get_graph() -> Any:
        """Return the orchagent graph builder (uncompiled).

        The router still owns checkpointer + compile decisions because they
        depend on per-request configuration.
        """
        return _get_orchagent_graph()

    # ---- Routing-policy helpers (rule-based; Phase 2 swaps to LLM-driven) ----
    @staticmethod
    def requires_coding_team(text: str) -> bool:
        return _requires_coding_team_for_text(text)

    @staticmethod
    def requires_human_approval(text: str) -> bool:
        return _requires_human_approval_for_text(text)

    # ---- Tool runtime context wrappers ----
    @staticmethod
    def set_runtime_context(context: ToolRuntimeContext) -> Any:
        return _set_tool_runtime_context(context)

    @staticmethod
    def get_runtime_context() -> ToolRuntimeContext:
        return _get_tool_runtime_context()

    @staticmethod
    def reset_runtime_context(token: Any) -> None:
        _reset_tool_runtime_context(token)

    @staticmethod
    def collect_runtime_artifacts() -> Any:
        return _collect_runtime_artifacts()
