from __future__ import annotations

from typing import Any, Callable

from langgraph.types import Command

from agent_core.state import BaseAgentState
from core.database import AsyncSessionLocal
from core.timezone import now_kst
from services.memory_service import MemoryService
from services.memory_store_service import MemoryStoreService


def make_load_memories_node() -> Callable:
    async def load_memories_node(state: BaseAgentState) -> Command:
        shared_context = state.get("shared_context", {}) or {}
        user_id = shared_context.get("current_user_id")
        thread_id = shared_context.get("thread_id")
        started_at = now_kst()

        if not isinstance(user_id, str) or not user_id or not isinstance(thread_id, str) or not thread_id:
            return Command(goto="planner")

        async with AsyncSessionLocal() as db:
            settings = await MemoryService.get_or_create_settings(db, user_id)
            if not settings.memory_enabled or not settings.allow_chat_history_reference:
                return Command(
                    update={
                        "shared_context": {
                            "personalization": {
                                "enabled": False,
                                "context_block": "",
                            },
                            "personalization_meta": {
                                "memory_ids": [],
                                "hit_count": 0,
                                "source": "disabled",
                                "retrieval_ms": 0,
                            },
                        }
                    },
                    goto="planner",
                )
            active_count = await MemoryService.count_active_memories(db, user_id=user_id)
            if active_count == 0:
                return Command(
                    update={
                        "shared_context": {
                            "personalization": {
                                "enabled": True,
                                "context_block": "",
                            },
                            "personalization_meta": {
                                "memory_ids": [],
                                "hit_count": 0,
                                "active_memory_count": 0,
                                "source": "empty",
                                "retrieval_ms": 0,
                            },
                        }
                    },
                    goto="planner",
                )

        context_block, memory_ids = MemoryStoreService.build_personalization_context(
            user_id=user_id,
            thread_id=thread_id,
        )
        retrieval_ms = max(
            int((now_kst() - started_at).total_seconds() * 1000),
            0,
        )

        return Command(
            update={
                "shared_context": {
                    "personalization": {
                        "enabled": True,
                        "context_block": context_block,
                    },
                    "personalization_meta": {
                        "memory_ids": [str(memory_id) for memory_id in memory_ids],
                        "hit_count": len(memory_ids),
                        "active_memory_count": active_count,
                        "source": "langgraph_postgres_store",
                        "retrieval_ms": retrieval_ms,
                    },
                }
            },
            goto="planner",
        )

    return load_memories_node
