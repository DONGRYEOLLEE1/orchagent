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
        class Router(TypedDict):
            next: Literal[tuple(options)]
            content: str # Added to allow supervisor to respond directly
        
        print(f"[Supervisor] Processing next turn... Members: {members}", flush=True)
        system_prompt_plus = (
            f"{system_prompt}\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. For any questions about current events, news, or topics that require the latest information (e.g., wars, politics, stock market), "
            "you MUST delegate to the 'research_team'. Do not attempt to answer from your own internal knowledge.\n"
            "2. If you can answer simple greetings or general common sense directly, "
            "provide your answer in the 'content' field and set 'next' to 'FINISH'.\n"
            "3. Always prioritize using specialized workers over answering yourself for complex tasks."
        )
        
        messages = [{"role": "system", "content": system_prompt_plus}] + state['messages']
        response = llm.with_structured_output(Router).invoke(messages)
        goto = response['next']
        content = response.get('content', "")
        
        print(f"[Supervisor] Routing decision: {goto}", flush=True)
        if content:
            print(f"[Supervisor] Response content: {content[:50]}...", flush=True)
        
        if goto == "FINISH":
            goto = END
            
        update_data = {"next": goto}
        if content:
            # Add the supervisor's response to the message history
            from langchain_core.messages import AIMessage
            update_data["messages"] = [AIMessage(content=content, name="supervisor")]
            
        return Command(
            update=update_data,
            goto=goto
        )
        
    return supervisor_node
