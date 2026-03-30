from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.memory_service import MemoryService
from services.memory_store_service import MemoryStoreService
from services.personalization_instruction_service import (
    PersonalizationInstructionService,
)


class PersonalizationService:
    @staticmethod
    def _collapse_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())

    @staticmethod
    def _instruction_line(title: str, content_text: str) -> str:
        normalized_title = PersonalizationService._collapse_text(title)
        normalized_content = PersonalizationService._collapse_text(content_text)
        if normalized_title:
            return f"- {normalized_title}: {normalized_content}"
        return f"- {normalized_content}"

    @staticmethod
    def _build_instruction_block(instructions: list[Any]) -> str:
        lines = [
            PersonalizationService._instruction_line(
                instruction.title,
                instruction.content_text,
            )
            for instruction in instructions
            if PersonalizationService._collapse_text(instruction.content_text)
        ]
        return "\n".join(lines)

    @staticmethod
    async def build_runtime_payload(
        db: AsyncSession,
        *,
        user_id: str,
        thread_id: str,
    ) -> dict[str, Any]:
        settings = await MemoryService.get_or_create_settings(db, user_id)
        instructions_enabled = bool(settings.instructions_enabled)
        memory_path_enabled = bool(
            settings.memory_enabled and settings.allow_chat_history_reference
        )

        instructions = []
        if instructions_enabled:
            instructions = await PersonalizationInstructionService.list_instructions(
                db,
                user_id=user_id,
                enabled_only=True,
            )

        profile_instructions = [
            instruction
            for instruction in instructions
            if instruction.instruction_type == "user_profile"
        ]
        response_preference_instructions = [
            instruction
            for instruction in instructions
            if instruction.instruction_type == "response_style"
        ]

        profile_block = PersonalizationService._build_instruction_block(
            profile_instructions
        )
        instructions_block = PersonalizationService._build_instruction_block(
            response_preference_instructions
        )

        memory_payload: dict[str, Any] = {
            "context_block": "",
            "memory_ids": [],
            "hit_count": 0,
            "summary_used": False,
            "recent_used": False,
            "cache_hit": False,
        }
        active_memory_count = 0
        if memory_path_enabled:
            active_memory_count = await MemoryService.count_active_memories(
                db,
                user_id=user_id,
            )
            if active_memory_count > 0:
                memory_payload = MemoryStoreService.build_personalization_payload(
                    user_id=user_id,
                    thread_id=thread_id,
                )

        memory_block = PersonalizationService._collapse_text(
            memory_payload.get("context_block")
        )
        if "\n" in str(memory_payload.get("context_block") or ""):
            memory_block = "\n".join(
                line.strip()
                for line in str(memory_payload.get("context_block") or "").splitlines()
                if line.strip()
            )

        has_instruction_blocks = bool(profile_block or instructions_block)
        has_memory_block = bool(memory_block)
        if has_instruction_blocks and has_memory_block:
            source = "hybrid_personalization"
        elif has_instruction_blocks:
            source = "sql_personalization_instructions"
        elif memory_path_enabled and active_memory_count == 0:
            source = "empty"
        elif has_memory_block:
            source = "langgraph_postgres_store"
        else:
            source = "disabled"

        memory_ids = memory_payload.get("memory_ids", [])
        return {
            "personalization": {
                "enabled": bool(has_instruction_blocks or has_memory_block),
                "profile_block": profile_block,
                "instructions_block": instructions_block,
                "memory_block": memory_block,
                # Keep the legacy alias during the renderer transition window.
                "context_block": memory_block,
            },
            "personalization_meta": {
                "memory_ids": [str(memory_id) for memory_id in memory_ids],
                "hit_count": len(memory_ids),
                "active_memory_count": active_memory_count,
                "source": source,
                "summary_used": memory_payload.get("summary_used", False),
                "recent_used": memory_payload.get("recent_used", False),
                "cache_hit": memory_payload.get("cache_hit", False),
                "hit_miss": "hit" if memory_ids else "miss",
                "context_chars": len(memory_block),
                "instruction_ids": [str(instruction.id) for instruction in instructions],
                "instruction_count": len(instructions),
                "instructions_enabled": instructions_enabled,
                "profile_count": len(profile_instructions),
                "response_preference_count": len(response_preference_instructions),
            },
        }
