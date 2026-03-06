from typing import Literal, List, Callable, Any
from typing_extensions import TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import Command
from langgraph.graph import END

from agent_core.state import BaseAgentState

def make_supervisor_node(llm: BaseChatModel, members: List[str], system_prompt_template: str = None) -> Callable:
    """
    Creates a supervisor node that manages workflow routing between multiple agents.
    Acts as an intelligent router using Command.
    """
    options = ["FINISH"] + members
    
    if not system_prompt_template:
        system_prompt = (
            f"You're a supervisor tasked with managing a conversation between the following workers: {members}. "
            "Given the following user request, respond with the worker to act next. "
            "Each worker will perform a task and respond with their results and status. "
            "When finished, respond with FINISH."
        )
    else:
        system_prompt = system_prompt_template.format(members=members)
        
    def supervisor_node(state: BaseAgentState) -> Command:
        # Create Router class dynamically because of dynamic Literal options
        Router = TypedDict("Router", {"next": Literal[tuple(options)]})
        
        messages = [{"role": "system", "content": system_prompt}] + state['messages']
        response = llm.with_structured_output(Router).invoke(messages)
        goto = response['next']
        
        if goto == "FINISH":
            goto = END
            
        return Command(
            update={"next": goto},
            goto=goto
        )
        
    return supervisor_node
