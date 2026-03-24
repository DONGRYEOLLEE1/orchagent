from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from core.config import settings
from prompt_kit.prompts import THREAD_TITLE_SUMMARIZER_PROMPT


class ThreadTitleResult(BaseModel):
    title: str = Field(description="A short one-line thread title.")


class ThreadTitleService:
    TITLE_MAX_LENGTH = 24
    FALLBACK_MAX_LENGTH = 80
    TRANSCRIPT_MAX_LENGTH = 6000
    UNTITLED_THREAD = "Untitled chat"

    @staticmethod
    def _collapse_text(content: str | None) -> str:
        if not content:
            return ""
        return " ".join(content.split())

    @staticmethod
    def _truncate(content: str, limit: int) -> str:
        normalized = ThreadTitleService._collapse_text(content)
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(limit - 3, 1)].rstrip() + "..."

    @staticmethod
    def fallback_title(message: str) -> str:
        normalized = ThreadTitleService._collapse_text(message)
        if not normalized:
            return ThreadTitleService.UNTITLED_THREAD
        return ThreadTitleService._truncate(
            normalized, ThreadTitleService.FALLBACK_MAX_LENGTH
        )

    @staticmethod
    def build_thread_transcript(messages: list[tuple[str, str]]) -> str:
        if not messages:
            return ""

        lines: list[str] = []
        for role, content in messages:
            normalized = ThreadTitleService._collapse_text(content)
            if not normalized:
                continue
            speaker = "User" if role == "user" else "Assistant"
            lines.append(f"{speaker}: {normalized}")

        transcript = "\n".join(lines).strip()
        if len(transcript) <= ThreadTitleService.TRANSCRIPT_MAX_LENGTH:
            return transcript

        return transcript[-ThreadTitleService.TRANSCRIPT_MAX_LENGTH :]

    @staticmethod
    def normalize_title(title: str | None, *, fallback_message: str) -> str:
        collapsed = ThreadTitleService._collapse_text(title)
        if not collapsed:
            return ThreadTitleService.fallback_title(fallback_message)

        cleaned = collapsed.replace('"', "").replace("'", "")
        cleaned = cleaned.rstrip(".,!?;:")
        cleaned = cleaned.replace(":", " ")
        cleaned = ThreadTitleService._collapse_text(cleaned)
        if not cleaned:
            return ThreadTitleService.fallback_title(fallback_message)

        if len(cleaned) > ThreadTitleService.TITLE_MAX_LENGTH:
            cleaned = cleaned[: ThreadTitleService.TITLE_MAX_LENGTH].rstrip()

        cleaned = cleaned.strip()
        if not cleaned:
            return ThreadTitleService.fallback_title(fallback_message)
        return cleaned

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_model():
        return init_chat_model(
            model=settings.THREAD_TITLE_MODEL,
            model_provider="openai",
            reasoning={"effort": "minimal"},
        )

    @staticmethod
    async def generate_title(message: str) -> str:
        normalized_message = ThreadTitleService._collapse_text(message)
        if not normalized_message:
            return ThreadTitleService.UNTITLED_THREAD

        model = ThreadTitleService._get_model()
        messages = [
            {"role": "system", "content": THREAD_TITLE_SUMMARIZER_PROMPT.template},
            {"role": "user", "content": normalized_message},
        ]
        result = await model.with_structured_output(ThreadTitleResult).ainvoke(messages)
        if not isinstance(result, ThreadTitleResult):
            result = ThreadTitleResult.model_validate(result)

        return ThreadTitleService.normalize_title(
            result.title,
            fallback_message=normalized_message,
        )

    @staticmethod
    async def generate_title_from_transcript(
        messages: list[tuple[str, str]], *, fallback_message: str
    ) -> str:
        transcript = ThreadTitleService.build_thread_transcript(messages)
        if not transcript:
            return ThreadTitleService.fallback_title(fallback_message)

        model = ThreadTitleService._get_model()
        prompt_input = (
            "Conversation transcript:\n"
            f"{transcript}\n\n"
            "Create a short sidebar thread title that reflects the dominant topic."
        )
        result = await model.with_structured_output(ThreadTitleResult).ainvoke(
            [
                {"role": "system", "content": THREAD_TITLE_SUMMARIZER_PROMPT.template},
                {"role": "user", "content": prompt_input},
            ]
        )
        if not isinstance(result, ThreadTitleResult):
            result = ThreadTitleResult.model_validate(result)

        return ThreadTitleService.normalize_title(
            result.title,
            fallback_message=fallback_message,
        )
