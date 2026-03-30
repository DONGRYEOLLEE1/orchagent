from __future__ import annotations

from typing import Any, Callable

from langgraph.types import Command

from agent_core.state import BaseAgentState
from core.database import AsyncSessionLocal
from core.timezone import now_kst
from services.personalization_service import PersonalizationService


def make_load_memories_node() -> Callable:
    async def load_memories_node(state: BaseAgentState) -> Command:
        shared_context = state.get("shared_context", {}) or {}
        user_id = shared_context.get("current_user_id")
        thread_id = shared_context.get("thread_id")
        started_at = now_kst()

        if not isinstance(user_id, str) or not user_id or not isinstance(thread_id, str) or not thread_id:
            return Command(goto="planner")

        async with AsyncSessionLocal() as db:
            runtime_payload = await PersonalizationService.build_runtime_payload(
                db,
                user_id=user_id,
                thread_id=thread_id,
            )

        retrieval_ms = max(
            int((now_kst() - started_at).total_seconds() * 1000),
            0,
        )
        runtime_payload["personalization_meta"]["retrieval_ms"] = retrieval_ms

        return Command(
            update={
                "shared_context": {
                    "personalization": runtime_payload["personalization"],
                    "personalization_meta": runtime_payload["personalization_meta"],
                }
            },
            goto="planner",
        )

    return load_memories_node
