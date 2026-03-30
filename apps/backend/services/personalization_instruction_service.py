from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_memory import KST, UserPersonalizationInstruction


class PersonalizationInstructionValidationError(ValueError):
    pass


class PersonalizationInstructionService:
    ALLOWED_TYPES = {"response_style", "user_profile"}
    TYPE_SORT_ORDER = {
        "user_profile": 0,
        "response_style": 1,
    }
    _BLOCKED_PATTERNS = (
        re.compile(
            r"(ignore|override|bypass|skip|disable|무시|우회|생략|해제).{0,32}(system|developer|policy|policies|security|safety|규칙|정책|보안|안전)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(approval|approve|승인).{0,24}(without|bypass|skip|ignore|없이|우회|생략)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(tool|tools|browser|web search|search|filesystem|file edit|shell|bash|python|command|웹 ?검색|파일 수정|셸 명령|도구).{0,32}(never|always|must|forbid|disable|하지 마|항상|반드시|금지|끄)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(system prompt|developer message|internal rule|시스템 프롬프트|개발자 메시지|내부 규칙)",
            re.IGNORECASE,
        ),
    )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(KST)

    @staticmethod
    def _collapse_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())

    @staticmethod
    def normalize_instruction_type(value: str | None) -> str:
        normalized = PersonalizationInstructionService._collapse_text(value).lower()
        if normalized not in PersonalizationInstructionService.ALLOWED_TYPES:
            raise PersonalizationInstructionValidationError(
                "Instruction type must be one of: response_style, user_profile."
            )
        return normalized

    @staticmethod
    def validate_instruction_text(*, title: str, content_text: str) -> None:
        combined = f"{title}\n{content_text}".strip()
        for pattern in PersonalizationInstructionService._BLOCKED_PATTERNS:
            if pattern.search(combined):
                raise PersonalizationInstructionValidationError(
                    "Instruction text cannot override approval, tool, or system policy behavior."
                )

    @staticmethod
    def sanitize_instruction_fields(
        *,
        instruction_type: str,
        title: str,
        content_text: str,
    ) -> tuple[str, str, str]:
        normalized_type = PersonalizationInstructionService.normalize_instruction_type(
            instruction_type
        )
        normalized_title = PersonalizationInstructionService._collapse_text(title)
        normalized_content = PersonalizationInstructionService._collapse_text(content_text)
        if not normalized_title:
            raise PersonalizationInstructionValidationError("Instruction title is required.")
        if not normalized_content:
            raise PersonalizationInstructionValidationError("Instruction content is required.")
        PersonalizationInstructionService.validate_instruction_text(
            title=normalized_title,
            content_text=normalized_content,
        )
        return normalized_type, normalized_title, normalized_content

    @staticmethod
    async def list_instructions(
        db: AsyncSession,
        *,
        user_id: str,
        enabled_only: bool = False,
    ) -> list[UserPersonalizationInstruction]:
        stmt = select(UserPersonalizationInstruction).where(
            UserPersonalizationInstruction.user_id == user_id
        )
        if enabled_only:
            stmt = stmt.where(UserPersonalizationInstruction.enabled.is_(True))
        stmt = stmt.order_by(
            asc(UserPersonalizationInstruction.instruction_type),
            asc(UserPersonalizationInstruction.created_at),
            asc(UserPersonalizationInstruction.id),
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return sorted(
            rows,
            key=lambda row: (
                PersonalizationInstructionService.TYPE_SORT_ORDER.get(
                    row.instruction_type, 99
                ),
                row.created_at,
                str(row.id),
            ),
        )

    @staticmethod
    async def create_instruction(
        db: AsyncSession,
        *,
        user_id: str,
        instruction_type: str,
        title: str,
        content_text: str,
        enabled: bool = True,
    ) -> UserPersonalizationInstruction:
        normalized_type, normalized_title, normalized_content = (
            PersonalizationInstructionService.sanitize_instruction_fields(
                instruction_type=instruction_type,
                title=title,
                content_text=content_text,
            )
        )
        instruction = UserPersonalizationInstruction(
            user_id=user_id,
            instruction_type=normalized_type,
            title=normalized_title,
            content_text=normalized_content,
            enabled=enabled,
        )
        db.add(instruction)
        await db.commit()
        await db.refresh(instruction)
        return instruction

    @staticmethod
    async def update_instruction(
        db: AsyncSession,
        *,
        user_id: str,
        instruction_id: UUID,
        instruction_type: str | None = None,
        title: str | None = None,
        content_text: str | None = None,
        enabled: bool | None = None,
    ) -> UserPersonalizationInstruction | None:
        result = await db.execute(
            select(UserPersonalizationInstruction).where(
                UserPersonalizationInstruction.id == instruction_id,
                UserPersonalizationInstruction.user_id == user_id,
            )
        )
        instruction = result.scalar_one_or_none()
        if instruction is None:
            return None

        next_type = (
            instruction.instruction_type
            if instruction_type is None
            else instruction_type
        )
        next_title = instruction.title if title is None else title
        next_content = instruction.content_text if content_text is None else content_text
        normalized_type, normalized_title, normalized_content = (
            PersonalizationInstructionService.sanitize_instruction_fields(
                instruction_type=next_type,
                title=next_title,
                content_text=next_content,
            )
        )

        instruction.instruction_type = normalized_type
        instruction.title = normalized_title
        instruction.content_text = normalized_content
        if enabled is not None:
            instruction.enabled = enabled
        instruction.updated_at = PersonalizationInstructionService._now()

        await db.commit()
        await db.refresh(instruction)
        return instruction

    @staticmethod
    async def delete_instruction(
        db: AsyncSession, *, user_id: str, instruction_id: UUID
    ) -> UserPersonalizationInstruction | None:
        result = await db.execute(
            select(UserPersonalizationInstruction).where(
                UserPersonalizationInstruction.id == instruction_id,
                UserPersonalizationInstruction.user_id == user_id,
            )
        )
        instruction = result.scalar_one_or_none()
        if instruction is None:
            return None

        await db.delete(instruction)
        await db.commit()
        return instruction
