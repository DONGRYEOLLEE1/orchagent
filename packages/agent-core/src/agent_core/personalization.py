from __future__ import annotations

from typing import Any

from prompt_kit.prompts import (
    PERSONALIZATION_INSTRUCTIONS_HEADING,
    PERSONALIZATION_MEMORY_HEADING,
    PERSONALIZATION_POLICY_HEADING,
    PERSONALIZATION_POLICY_PROMPT,
    PERSONALIZATION_PROFILE_HEADING,
)


def _normalize_block(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def build_personalization_prompt_block(shared_context: dict[str, Any] | None) -> str:
    personalization = (shared_context or {}).get("personalization") or {}
    if not personalization.get("enabled"):
        return ""

    profile_block = _normalize_block(personalization.get("profile_block"))
    instructions_block = _normalize_block(personalization.get("instructions_block"))
    memory_block = _normalize_block(
        personalization.get("memory_block") or personalization.get("context_block")
    )

    sections: list[str] = []
    if profile_block:
        sections.append(f"{PERSONALIZATION_PROFILE_HEADING}:\n{profile_block}")
    if instructions_block:
        sections.append(
            f"{PERSONALIZATION_INSTRUCTIONS_HEADING}:\n{instructions_block}"
        )
    if memory_block:
        sections.append(f"{PERSONALIZATION_MEMORY_HEADING}:\n{memory_block}")

    if not sections:
        return ""

    sections.append(
        f"{PERSONALIZATION_POLICY_HEADING}:\n"
        f"{PERSONALIZATION_POLICY_PROMPT.template.strip()}"
    )
    return "\n\n" + "\n\n".join(sections)
