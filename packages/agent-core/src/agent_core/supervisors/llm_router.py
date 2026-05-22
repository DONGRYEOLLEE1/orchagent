"""LLM-driven router that emits a structured ``RouterDecision``.

Phase 2.4 of the codebase-wide refactor. Plan §4.0 P1 says **all routing
decisions are made by an LLM**; the supervisor surface around it is
limited to safeguards (P3) and observability (P4). This module is the
single place where:

1. The supervisor's system prompt is composed (members + task plan +
   personalization + the routing-decision guidance fragment).
2. The LLM is invoked via :meth:`with_structured_output` so the response
   is guaranteed to be a :class:`RouterDecision` (or we know it failed).
3. The decision is run through the safeguard chain that may **block**
   (force FINISH) or **request a retry**, but never silently rewrite a
   valid routing choice.

The function returns ``(RouterDecision, RouterStatus)`` so callers can
log the safety outcome on the state and/or emit it as an SSE route event
without having to re-derive it.
"""

from __future__ import annotations

from typing import Any, Iterable

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from agent_core.config import SAFEGUARDS
from agent_core.personalization import build_personalization_prompt_block
from agent_core.router_schema import RouterDecision, RouterStatus
from agent_core.safeguards import (
    enforce_dispatch_limit,
    enforce_team_redirect_limit,
    fallback_decision_on_parse_failure,
    reject_invalid_goto,
)


def compose_system_prompt(
    base_prompt: str,
    *,
    layer: str,
    task_plan: str | None,
    shared_context: dict[str, Any] | None,
) -> str:
    """Build the final system prompt the router LLM sees.

    The head supervisor receives the task plan; team supervisors do not
    (the task plan is global to the turn). Personalization always rides
    along so direct-FINISH answers stay on-brand.
    """
    personalization_block = build_personalization_prompt_block(shared_context or {})
    plan_block = ""
    if layer == "head" and task_plan and task_plan != "NO_PLAN":
        plan_block = (
            f"\n\nCURRENT TASK PLAN:\n{task_plan}\n"
            "Review the plan above and the conversation history. Decide which "
            "worker is best suited for the NEXT step of the plan. If the plan "
            "is complete or you can finish it yourself, respond with FINISH."
        )
    return f"{base_prompt}{plan_block}{personalization_block}"


async def decide_route(
    llm: BaseChatModel,
    *,
    system_prompt: str,
    messages: list[Any],
    allowed_nodes: Iterable[str],
    layer: str,
    same_team_streak: int = 0,
    dispatch_count: int = 0,
    max_team_dispatches: int | None = None,
) -> tuple[RouterDecision, RouterStatus]:
    """Run the structured-output LLM router and apply the safeguard chain.

    Parameters mirror the slice of state each safeguard needs so this
    function stays pure and easy to unit-test. The caller owns building
    up ``messages`` (system prompt + chat history) and computing the
    bookkeeping counters from state.
    """
    request = [{"role": "system", "content": system_prompt}, *messages]
    structured_llm = llm.with_structured_output(RouterDecision)

    # plan §4.0.5: "LLM structured output 파싱 실패 → 1회 재요청 → 그래도
    # 실패면 FINISH". OpenAI Responses API + langchain structured output
    # 조합에서 가끔 ``parsed`` 필드 없이 raw text content를 emit하는데,
    # (1) 한 번 재시도하고, (2) 그래도 실패하면 raw error 메시지 안에 박힌
    # JSON을 직접 추출해 RouterDecision으로 복원한다.
    response: Any = None
    last_error: Any = None
    decision: RouterDecision | None = None
    for attempt in range(2):
        try:
            response = await structured_llm.ainvoke(request)
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = exc
            response = None
            continue
        decision_attempt = _coerce_to_router_decision(response)
        if decision_attempt is not None:
            decision = decision_attempt
            break

    if decision is None:
        # Tier-3 recovery: try to extract the JSON RouterDecision that OpenAI
        # emitted as a raw text content block. The text is reflected back in
        # the langchain ValueError message, so we can salvage it without
        # making a third LLM round-trip. This keeps multi-turn follow-up
        # requests usable when the provider intermittently bypasses its own
        # ``parsed`` field.
        salvaged = _salvage_router_decision_from_error(last_error)
        if salvaged is not None:
            decision = salvaged

    if decision is None:
        raw_text = repr(last_error) if last_error is not None else str(response)
        return fallback_decision_on_parse_failure(raw_text=raw_text), "parse_failed"

    # Safeguard 1 — invalid `next` value gets forced to FINISH.
    outcome = reject_invalid_goto(decision, allowed_nodes)
    if outcome.status != "accepted":
        return outcome.decision, outcome.status

    # Safeguard 2 — head-layer ping-pong on the same team.
    if layer == "head" and outcome.decision.next.endswith("_team"):
        outcome = enforce_team_redirect_limit(
            outcome.decision,
            same_team_streak=same_team_streak,
            limit=SAFEGUARDS.head_team_redirect_limit,
        )
        if outcome.status != "accepted":
            return outcome.decision, outcome.status

    # Safeguard 3 — team-layer dispatch budget.
    if layer == "team" and max_team_dispatches is not None:
        outcome = enforce_dispatch_limit(
            outcome.decision,
            dispatch_count=dispatch_count,
            limit=max_team_dispatches,
        )
        if outcome.status != "accepted":
            return outcome.decision, outcome.status

    return outcome.decision, "accepted"


def _salvage_router_decision_from_error(error: Any) -> RouterDecision | None:
    """Best-effort recovery when OpenAI Responses API skips the ``parsed`` field.

    The provider sometimes emits a valid JSON ``RouterDecision`` blob inside
    a raw text content block instead of populating the structured ``parsed``
    field, and langchain raises ``ValueError`` that includes the original
    message. We scan that message for the first balanced JSON object and try
    to validate it against ``RouterDecision``. Returning ``None`` here means
    the caller should fall back to the safeguard FINISH.
    """
    if error is None:
        return None
    import json
    import re

    message = repr(error)
    # Greedy match the first JSON object that mentions a ``next`` key.
    # Balanced-braces regex is hard in Python's ``re``; we instead find every
    # ``{...}`` chunk and try them in order until one parses cleanly.
    for candidate in re.findall(r"\{[^{}]*\}", message):
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict) or "next" not in payload:
            continue
        try:
            return RouterDecision.model_validate(payload)
        except ValidationError:
            continue
    return None


def _coerce_to_router_decision(raw: Any) -> RouterDecision | None:
    """Best-effort coercion of LangChain's structured-output return value.

    ``with_structured_output(RouterDecision)`` should yield a
    ``RouterDecision`` directly, but providers occasionally hand back a
    plain dict (notably under structured-output retries). Accept both
    shapes so test stubs and real providers behave identically.
    """
    if isinstance(raw, RouterDecision):
        return raw
    if isinstance(raw, dict):
        try:
            return RouterDecision.model_validate(raw)
        except ValidationError:
            return None
    # Some providers wrap the parsed result in a ``parsed`` attribute.
    parsed = getattr(raw, "parsed", None)
    if isinstance(parsed, RouterDecision):
        return parsed
    if isinstance(parsed, dict):
        try:
            return RouterDecision.model_validate(parsed)
        except ValidationError:
            return None
    return None


__all__ = ["compose_system_prompt", "decide_route"]
