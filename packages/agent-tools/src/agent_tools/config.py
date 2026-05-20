"""Shared timeout / limit policy for worker tools.

Phase 4.4 of the codebase-wide refactor. Each worker tool used to hard-code
its own timeout (``coding.py`` ran shells with ``timeout=180``, ``web.py``
issued HTTP requests with ``timeout=12``). Pulling those into a single
dataclass keeps the contract auditable and lets ops tune timeouts without
re-deploying. Defaults preserve the prior behaviour exactly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class ToolTimeouts:
    """Per-domain tool timeouts (seconds)."""

    coding_subprocess_seconds: int = _env_int("TOOL_TIMEOUT_CODING", 180)
    web_http_seconds: int = _env_int("TOOL_TIMEOUT_WEB", 12)
    runtime_context_default_seconds: int = _env_int(
        "TOOL_TIMEOUT_DEFAULT", 60
    )


TIMEOUTS = ToolTimeouts()


__all__ = ["TIMEOUTS", "ToolTimeouts"]
