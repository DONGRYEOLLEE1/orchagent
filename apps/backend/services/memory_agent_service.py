from __future__ import annotations

from functools import lru_cache
import re
from uuid import UUID

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import AsyncSessionLocal
from core.timezone import iso_now_kst
from prompt_kit.prompts import MEMORY_EXTRACTOR_PROMPT
from services.memory_service import MemoryCandidate, MemoryService
from services.trace_service import TraceService


class MemoryCandidatePayload(BaseModel):
    category: str = Field(description="Memory category.")
    title: str = Field(description="Short UI-friendly title.")
    content_text: str = Field(description="A compact durable memory statement in Korean.")
    scope_type: str = Field(description="Either user_global or thread_local.")
    confidence: int = Field(description="0-100 confidence score.")
    salience: int = Field(description="0-100 salience score.")


class MemoryExtractionResult(BaseModel):
    candidates: list[MemoryCandidatePayload] = Field(
        default_factory=list,
        description="Zero or more durable user memory candidates.",
    )


class MemoryAgentService:
    FIRST_PERSON_SIGNAL = re.compile(
        r"(?:\bI\b|\bI'm\b|\bI am\b|\bmy\b|\bmine\b|난|나는|내가|내 취향|제가|저는|좋아해|좋아한다|선호|싫어|항상|보통|자주|가급적)",
        re.IGNORECASE,
    )
    ALLOWED_CATEGORIES = {
        "language_preference",
        "response_format",
        "tone_style",
        "technical_stack",
        "domain_interest",
        "workflow_preference",
        "ongoing_goal",
        "personal_interest",
    }
    BLOCKED_PATTERNS = [
        re.compile(r"password|비밀번호|token|토큰|secret|시크릿", re.IGNORECASE),
        re.compile(r"주민등록|여권|계좌|카드번호", re.IGNORECASE),
        re.compile(
            r"for this turn|just this turn|just this once|temporary|temporarily|이번 턴|이번 요청|지금만|이번에만|임시로",
            re.IGNORECASE,
        ),
        re.compile(
            r"(approval|승인).{0,24}(without|bypass|skip|없이|우회|생략)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(ignore|override|bypass|skip|무시|우회|생략).{0,32}(system|developer|policy|security|safety|규칙|정책|보안|안전)",
            re.IGNORECASE,
        ),
    ]
    MIN_CONFIDENCE = 70

    @staticmethod
    def _collapse_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())

    @staticmethod
    def should_review_message(message: str) -> bool:
        collapsed = MemoryAgentService._collapse_text(message)
        if not collapsed:
            return False
        return bool(MemoryAgentService.FIRST_PERSON_SIGNAL.search(collapsed))

    @staticmethod
    def _is_blocked_text(value: str) -> bool:
        return any(pattern.search(value) for pattern in MemoryAgentService.BLOCKED_PATTERNS)

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_agent():
        model = init_chat_model(
            model=settings.MEMORY_AGENT_MODEL,
            model_provider="openai",
            reasoning={"effort": "low"},
        )
        return create_agent(
            model=model,
            tools=[],
            system_prompt=MEMORY_EXTRACTOR_PROMPT.template,
            response_format=MemoryExtractionResult,
            name="memory_agent",
        )

    @staticmethod
    async def extract_candidates(
        *, user_message: str, assistant_message: str | None = None
    ) -> list[MemoryCandidate]:
        collapsed_user = MemoryAgentService._collapse_text(user_message)
        collapsed_assistant = MemoryAgentService._collapse_text(assistant_message)
        if not MemoryAgentService.should_review_message(collapsed_user):
            return []

        agent = MemoryAgentService._get_agent()
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Latest user message:\n{collapsed_user}\n\n"
                            f"Latest assistant answer:\n{collapsed_assistant}"
                        ),
                    }
                ]
            }
        )
        structured = result.get("structured_response") if isinstance(result, dict) else None
        if structured is None:
            return []
        if not isinstance(structured, MemoryExtractionResult):
            structured = MemoryExtractionResult.model_validate(structured)

        candidates: list[MemoryCandidate] = []
        for candidate in structured.candidates:
            category = MemoryAgentService._collapse_text(candidate.category)
            title = MemoryAgentService._collapse_text(candidate.title)
            content_text = MemoryAgentService._collapse_text(candidate.content_text)
            scope_type = MemoryAgentService._collapse_text(candidate.scope_type) or "user_global"
            confidence = int(candidate.confidence or 0)
            salience = int(candidate.salience or 0)
            if category not in MemoryAgentService.ALLOWED_CATEGORIES:
                continue
            if scope_type not in {"user_global", "thread_local"}:
                continue
            if confidence < MemoryAgentService.MIN_CONFIDENCE:
                continue
            if not title or not content_text:
                continue
            if MemoryAgentService._is_blocked_text(title) or MemoryAgentService._is_blocked_text(content_text):
                continue
            candidates.append(
                MemoryCandidate(
                    category=category,
                    title=title,
                    content_text=content_text,
                    scope_type=scope_type,
                    confidence=confidence,
                    salience=salience,
                )
            )
        return candidates

    @staticmethod
    async def process_turn(
        db: AsyncSession,
        *,
        user_id: str,
        thread_id: str,
        turn_id: UUID | None,
        user_message: str,
        assistant_message: str | None = None,
    ) -> list[UUID]:
        settings_row = await MemoryService.get_or_create_settings(db, user_id)
        if not settings_row.memory_enabled or not settings_row.allow_inferred_memory:
            return []

        candidates = await MemoryAgentService.extract_candidates(
            user_message=user_message,
            assistant_message=assistant_message,
        )
        if not candidates:
            return []

        saved_ids: list[UUID] = []
        for candidate in candidates:
            memory, _ = await MemoryService.upsert_inferred_memory(
                db,
                user_id=user_id,
                candidate=candidate,
                thread_id=thread_id,
                created_from_turn_id=turn_id,
            )
            saved_ids.append(memory.id)
        return saved_ids

    @staticmethod
    async def run_sidecar_with_fresh_session(
        *,
        user_id: str,
        thread_id: str,
        turn_id: UUID | None,
        user_message: str,
        assistant_message: str | None,
    ) -> None:
        """Run process_turn + persist a memory_write trace in a fresh session.

        Mirrors the previous chat.py `_run_memory_agent_sidecar` helper so chat
        stream cleanup tasks call a single service entry point.
        """
        if turn_id is None:
            return

        async with AsyncSessionLocal() as db:
            saved_ids = await MemoryAgentService.process_turn(
                db,
                user_id=user_id,
                thread_id=thread_id,
                turn_id=turn_id,
                user_message=user_message,
                assistant_message=assistant_message,
            )
            if saved_ids:
                await TraceService.create_event(
                    db,
                    thread_id=thread_id,
                    event_type="memory_write",
                    node_name="memory_agent",
                    payload={
                        "event_type": "memory_write",
                        "saved_memory_ids": [str(memory_id) for memory_id in saved_ids],
                        "saved_count": len(saved_ids),
                        "user_message": user_message,
                        "assistant_message_present": bool(assistant_message),
                        "timestamp": iso_now_kst(),
                    },
                    user_id=user_id,
                    turn_id=turn_id,
                )
