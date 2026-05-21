"""Encapsulate the chat route's dependency on agent_core / workflow / agent_tools.

Phase 1.5 of the codebase-wide refactor. AGENTS.md forbids the router layer
from importing the orchestration packages directly. This service is the single
seam that the chat route uses to:

- compile the orchagent graph (``OrchestrationService.get_graph``)
- look up the default LLM model id (``OrchestrationService.DEFAULT_LLM_MODEL``)
- pre-flag a turn for coding workspace materialization or human-approval HITL
  (``requires_coding_team`` / ``requires_human_approval``) — these are
  **API-layer pre-flags** consumed by the chat route to decide whether to
  create a coding workspace or seed ``force_requires_approval`` in shared
  context. They are NOT used for graph routing decisions; the LLM router
  inside the supervisor owns routing exclusively (Phase 2.2 round 3).
- bind / read / clear the per-turn tool runtime context

``ToolAttachment`` and ``ToolRuntimeContext`` are re-exported so the router can
keep its existing type annotations without importing ``agent_tools.runtime``.
"""

from __future__ import annotations

import re
from typing import Any

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


# API-layer keyword pre-flags. The supervisor LLM router owns the actual
# routing decision; these helpers only let the chat route decide whether to
# materialize a coding workspace ahead of graph execution or to seed
# ``shared_context.force_requires_approval`` as a HITL safety net.
_CODING_PREFLAG_PATTERNS = [
    re.compile(
        r"\b(fix|debug|refactor|implement|code|coding|bug|test|tests|build|lint|compile|repo|repository|function|component|module|file|files)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(고쳐|수정|디버그|리팩터|구현|코드|버그|테스트|빌드|린트|레포|저장소|파일|함수|컴포넌트|모듈)",
        re.IGNORECASE,
    ),
]

_APPROVAL_PREFLAG_PATTERNS = [
    re.compile(
        r"\b(edit|modify|write|create|delete|remove|rename|overwrite|save|update)\b.*\b(file|files|filesystem|repo|repository|workspace|directory)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(run|execute)\b.*\b(code|script|command|shell|bash|python)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(shell command|bash command|python script|sql script|rm\s+-rf|chmod|chown|drop database|wipe)\b",
        re.IGNORECASE,
    ),
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

    # ---- API-layer pre-flags (chat route only; NOT routing decisions) ----
    @staticmethod
    def requires_coding_team(text: str) -> bool:
        """Pre-flag for coding workspace materialization.

        Used by ``_needs_coding_workspace`` to decide whether to create a
        per-turn workspace before invoking the graph. Over-flagging is safe
        (workspace is wasted) and under-flagging is safe (LLM router can
        still pick coding_team if appropriate, just without workspace).
        """
        return any(pattern.search(text or "") for pattern in _CODING_PREFLAG_PATTERNS)

    @staticmethod
    def requires_human_approval(text: str) -> bool:
        """Pre-flag for HITL approval guard.

        Seeds ``shared_context.force_requires_approval`` so the head
        supervisor's interrupt path triggers even when the LLM router missed
        the risk signal. The supervisor LLM remains the primary decider.
        """
        return any(pattern.search(text or "") for pattern in _APPROVAL_PREFLAG_PATTERNS)

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
