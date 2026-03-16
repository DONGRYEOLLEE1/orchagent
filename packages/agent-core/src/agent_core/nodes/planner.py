from typing import Callable
from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import Command
from langchain_core.messages import AIMessage
from prompt_kit.prompts import PLANNER_PROMPT

from agent_core.state import BaseAgentState


class TaskPlan(BaseModel):
    plan: str = Field(
        description="A detailed step-by-step markdown plan to fulfill the user's request. Keep it concise but comprehensive. If the task is too simple (e.g., greetings), just return 'NO_PLAN'."
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
