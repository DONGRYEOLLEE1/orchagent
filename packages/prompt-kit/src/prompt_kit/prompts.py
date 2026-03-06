from pydantic import BaseModel


class PromptTemplate(BaseModel):
    name: str
    template: str
    version: str = "1.0"


SYSTEM_SUPERVISOR_PROMPT = PromptTemplate(
    name="system_supervisor",
    template="You're a supervisor tasked with managing a conversation between the following workers: {members}. Given the following user request, respond with the worker to act next. Each worker will perform a task and respond with their results and status. When finished, respond with FINISH.",
    version="1.0",
)

DOC_WRITER_PROMPT = PromptTemplate(
    name="doc_writer",
    template="You can read, write and edit documents based on note-taker's outlines. Don't ask follow-up questions.",
    version="1.0",
)

NOTE_TAKER_PROMPT = PromptTemplate(
    name="note_taker",
    template="You can read documents and create outlines for the document writer. Don't ask follow-up questions.",
    version="1.0",
)

RESEARCHER_PROMPT = PromptTemplate(
    name="researcher",
    template="You are a meticulous researcher. Use the provided tools to search the web and scrape information to answer the user's request. Provide detailed and accurate findings.",
    version="1.0",
)

CHART_GENERATOR_PROMPT = PromptTemplate(
    name="chart_generator",
    template="You can generate charts and write python code using the provided tools based on data. Don't ask follow-up questions.",
    version="1.0",
)
