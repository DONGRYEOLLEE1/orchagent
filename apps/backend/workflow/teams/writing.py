from typing import Literal
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command
from agent_core.builder import TeamBuilder
from agent_core.state import BaseAgentState
from agent_tools.file_io import create_outline, read_document, write_document, edit_document, python_repl_tool

class WritingTeamBuilder(TeamBuilder):
    def register_nodes(self):
        # 1. Document Writer
        doc_writer_agent = create_react_agent(
            model=self.llm,
            tools=[write_document, edit_document, read_document],
            prompt="You can read, write and edit documents based on note-taker's outlines. Don't ask follow-up questions."
        )
        def doc_writing_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
            result = doc_writer_agent.invoke(state)
            return Command(
                update={"messages": [HumanMessage(content=result['messages'][-1].content, name="doc_writer")]},
                goto="supervisor"
            )
        self.builder.add_node("doc_writer", doc_writing_node)

        # 2. Note Taker
        note_taking_agent = create_react_agent(
            model=self.llm,
            tools=[create_outline, read_document],
            prompt="You can read documents and create outlines for the document writer. Don't ask follow-up questions."
        )
        def note_taking_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
            result = note_taking_agent.invoke(state)
            return Command(
                update={"messages": [HumanMessage(content=result['messages'][-1].content, name="note_taker")]},
                goto="supervisor"
            )
        self.builder.add_node("note_taker", note_taking_node)

        # 3. Chart Generator
        chart_generating_agent = create_react_agent(
            model=self.llm,
            tools=[read_document, python_repl_tool]
        )
        def chart_generating_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
            result = chart_generating_agent.invoke(state)
            return Command(
                update={"messages": [HumanMessage(content=result['messages'][-1].content, name="chart_generator")]},
                goto="supervisor"
            )
        self.builder.add_node("chart_generator", chart_generating_node)

def get_writing_graph(llm):
    return WritingTeamBuilder(llm, "WritingTeam", ["doc_writer", "note_taker", "chart_generator"]).build()
