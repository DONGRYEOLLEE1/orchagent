from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from core.config import settings
from prompt_kit.prompts import SUGGESTED_QUERIES_PROMPT


class SuggestedQueriesResult(BaseModel):
    suggestions: list[str] = Field(
        description="Three to four short follow-up questions for the user."
    )


class ThreadSuggestedQueryService:
    MAX_SUGGESTIONS = 4
    MAX_QUERY_LENGTH = 36

    @staticmethod
    def _collapse_text(content: str | None) -> str:
        if not content:
            return ""
        return " ".join(content.split())

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized = ThreadSuggestedQueryService._collapse_text(query)
        normalized = normalized.strip().strip('"').strip("'")
        normalized = normalized.rstrip(".,!?;:")
        if len(normalized) > ThreadSuggestedQueryService.MAX_QUERY_LENGTH:
            normalized = normalized[: ThreadSuggestedQueryService.MAX_QUERY_LENGTH].rstrip()
        return normalized

    @staticmethod
    def normalize_suggestions(queries: list[str] | None) -> list[str]:
        if not queries:
            return []

        normalized_queries: list[str] = []
        seen: set[str] = set()
        for query in queries:
            normalized = ThreadSuggestedQueryService._normalize_query(query)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_queries.append(normalized)
            if len(normalized_queries) >= ThreadSuggestedQueryService.MAX_SUGGESTIONS:
                break
        return normalized_queries

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_model():
        return init_chat_model(
            model=settings.THREAD_SUGGESTIONS_MODEL,
            model_provider="openai",
            reasoning={"effort": "minimal"},
        )

    @staticmethod
    async def generate_suggestions(
        *, user_message: str, assistant_message: str
    ) -> list[str]:
        normalized_user = ThreadSuggestedQueryService._collapse_text(user_message)
        normalized_assistant = ThreadSuggestedQueryService._collapse_text(assistant_message)
        if not normalized_user or not normalized_assistant:
            return []

        model = ThreadSuggestedQueryService._get_model()
        messages = [
            {"role": "system", "content": SUGGESTED_QUERIES_PROMPT.template},
            {
                "role": "user",
                "content": (
                    f"Latest user request:\n{normalized_user}\n\n"
                    f"Latest assistant answer:\n{normalized_assistant}"
                ),
            },
        ]
        result = await model.with_structured_output(SuggestedQueriesResult).ainvoke(
            messages
        )
        if not isinstance(result, SuggestedQueriesResult):
            result = SuggestedQueriesResult.model_validate(result)

        return ThreadSuggestedQueryService.normalize_suggestions(result.suggestions)
