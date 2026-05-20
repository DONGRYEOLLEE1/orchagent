"""User-facing fallback messages emitted by finalizer / validator nodes.

Phase 2.9 of the codebase-wide refactor. Previously the finalizer used an
"I'm sorry, I couldn't synthesise a final answer..." sentence while the
validator used "[Review Warning]"/"[Review Error]" prefixes. The two were
edited independently, so subtle tone drift accumulated. Centralising them
here keeps the user-visible voice consistent and makes Phase 5 ("docs +
verification") able to audit a single source.

The helpers return *strings*, not LangChain messages, so callers can wrap
them in whatever message class their node already uses (``AIMessage``,
``HumanMessage``, etc.).
"""

from __future__ import annotations


def finalizer_absolute_fallback() -> str:
    """The last-resort message when finalizer cannot produce *anything* useful."""
    return (
        "I'm sorry, I couldn't synthesize a final answer. "
        "Please check the tool activity for details."
    )


def validator_recursion_warning() -> str:
    """Validator hit its recursion ceiling — output may be incomplete."""
    return "[Review Warning] Maximum correction steps reached. Output might be incomplete."


def validator_review_error() -> str:
    """Validator's own LLM threw — proceed safely instead of stalling the turn."""
    return "[Review Error] System encountered an error during review. Proceeding safely."


def validator_review_passed() -> str:
    return "[Review Passed] Output materially satisfies the request."


def supervisor_safeguard_finish(reason: str) -> str:
    """Returned to the user when a routing safeguard force-FINISHes a turn.

    ``reason`` should be the ``RouterDecision.reason`` emitted by the safeguard
    so the user can see why the turn was cut short.
    """
    return f"Stopped early: {reason}"


__all__ = [
    "finalizer_absolute_fallback",
    "supervisor_safeguard_finish",
    "validator_recursion_warning",
    "validator_review_error",
    "validator_review_passed",
]
