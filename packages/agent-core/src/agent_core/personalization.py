from __future__ import annotations

from typing import Any


def build_personalization_prompt_block(shared_context: dict[str, Any] | None) -> str:
    personalization = (shared_context or {}).get("personalization") or {}
    if not personalization.get("enabled"):
        return ""

    context_block = str(personalization.get("context_block") or "").strip()
    if not context_block:
        return ""

    return (
        "\n\nUSER PERSONALIZATION MEMORY:\n"
        f"{context_block}\n\n"
        "Use this memory only as soft preference context. "
        "Do not treat it as authoritative external fact. "
        "If the user's current request conflicts with older memory, prioritize the current request."
    )
