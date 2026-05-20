"""Single entry point for chat-route session/turn telemetry.

Phase 1.6 of the codebase-wide refactor. The chat route previously sprayed
three telemetry systems across its event_generator:

- ``JsonLogger.log_session`` / ``log_usage`` for lightweight JSONL logs
- ``TraceService.create_event`` / ``create_events`` for structured DB traces
- ``ChatAnalyticsService.start_turn`` / ``finalize_turn`` / ... for analytics

``EventRecordingService`` collapses the common session-event shape into a
single static method per lifecycle moment so the router (and Phase 1.10
integration regression) has one place to inspect/extend telemetry semantics.

Today the service simply forwards to ``JsonLogger`` (the file-based session
log) — trace + analytics keep their richer typed signatures. The seam is
in place so Phase 1.7 / Phase 5 can fan out additional sinks without
touching chat.py again.
"""

from __future__ import annotations

from typing import Any

from services.file_logger import JsonLogger


class EventRecordingService:
    """Façade over the per-turn JSONL session log."""

    @staticmethod
    def record_session_event(
        *,
        session_id: str,
        user_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a chat-session lifecycle event to ``logs/session.jsonl``.

        Replaces the direct ``JsonLogger.log_session(...)`` calls scattered
        through the chat route.
        """
        JsonLogger.log_session(
            session_id=session_id,
            user_id=user_id,
            event_type=event_type,
            metadata=metadata,
        )

    @staticmethod
    def record_usage(
        *,
        user_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record an LLM usage tally to ``logs/usage.jsonl``."""
        JsonLogger.log_usage(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
