from pydantic import BaseModel

class PromptTemplate(BaseModel):
    name: str
    template: str
    version: str = "1.0"

SYSTEM_SUPERVISOR_PROMPT = PromptTemplate(
    name="system_supervisor",
    template="You're a supervisor tasked with managing a conversation between the following workers: {members}. Given the following user request, respond with the worker to act next. Each worker will perform a task and respond with their results and status. When finished, respond with FINISH.",
    version="1.0"
)
