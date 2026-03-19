from typing import Callable
from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import Command
from langchain_core.messages import AIMessage
from prompt_kit.prompts import PLANNER_PROMPT

from agent_core.state import BaseAgentState


class TaskPlan(BaseModel):
    plan: str = Field(
        description="A short markdown plan to fulfill the user's request. Prefer 2 steps for simple single-deliverable tasks. If the task is too simple (e.g., greetings), just return 'NO_PLAN'."
    )


def _extract_latest_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, tuple) and len(message) >= 2 and message[0] == "user":
            return str(message[1])

        message_type = getattr(message, "type", None)
        if message_type == "human":
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(str(item.get("text", "")))
                return " ".join(part for part in text_parts if part)

    return ""


def _build_simple_research_plan(user_text: str) -> str | None:
    normalized = user_text.lower()
    research_markers = (
        "웹검색",
        "웹 검색",
        "검색",
        "조사",
        "찾아",
        "알아봐",
        "search",
        "research",
        "look up",
        "web",
    )
    answer_markers = (
        "설명",
        "요약",
        "정리",
        "답변",
        "explain",
        "summary",
        "summarize",
    )
    complex_markers = (
        "보고서",
        "report",
        "table",
        "표",
        "비교",
        "compare",
        "slide",
        "발표",
        "코드",
        "파일",
        "문서",
        "article",
    )

    if not any(marker in normalized for marker in research_markers):
        return None
    if not any(marker in normalized for marker in answer_markers):
        return None
    if any(marker in normalized for marker in complex_markers):
        return None

    return (
        "1. [research_team] 사용자 요청을 답할 만큼만 신뢰할 수 있는 최신 자료를 조사한다.\n"
        "2. [writing_team] 조사 결과를 바탕으로 요청한 언어/분량/형식에 맞춰 최종 답변을 작성한다."
    )


def make_planner_node(llm: BaseChatModel) -> Callable:
    """
    Creates a planner node that executes immediately after user input.
    It decomposes complex requests into a markdown plan and saves it to state.
    """
    system_prompt = PLANNER_PROMPT.template

    async def planner_node(state: BaseAgentState) -> Command:
        print("[Planner] Analyzing request and creating plan...", flush=True)

        # If there's already a plan and we are just looping, we don't recreate it unless explicitly asked.
        # But usually Planner is only called once at START, or we can check if it's the first turn.
        if state.get("task_plan"):
            print("[Planner] Plan already exists. Skipping.", flush=True)
            return Command(goto="head_supervisor")

        latest_user_text = _extract_latest_user_text(state.get("messages", []))
        simple_research_plan = _build_simple_research_plan(latest_user_text)
        if simple_research_plan:
            print(
                f"[Planner] Using lightweight plan:\n{simple_research_plan}", flush=True
            )
            plan_message = AIMessage(
                content=f"**[Planner] Proposed Execution Plan:**\n{simple_research_plan}",
                name="planner",
            )
            return Command(
                update={"task_plan": simple_research_plan, "messages": [plan_message]},
                goto="head_supervisor",
            )

        messages = [{"role": "system", "content": system_prompt}] + state.get(
            "messages", []
        )

        try:
            from typing import cast

            result = cast(
                TaskPlan,
                await llm.with_structured_output(TaskPlan).ainvoke(messages),
            )
            plan = result.plan

            if plan == "NO_PLAN" or not plan.strip():
                print("[Planner] No complex plan needed.", flush=True)
                return Command(goto="head_supervisor")

            print(f"[Planner] Generated Plan:\n{plan}", flush=True)

            # Save the plan to state and notify the user/supervisor via message
            plan_message = AIMessage(
                content=f"**[Planner] Proposed Execution Plan:**\n{plan}",
                name="planner",
            )

            return Command(
                update={"task_plan": plan, "messages": [plan_message]},
                goto="head_supervisor",
            )
        except Exception as e:
            print(f"[Planner] Error creating plan: {e}", flush=True)
            return Command(goto="head_supervisor")

    return planner_node
