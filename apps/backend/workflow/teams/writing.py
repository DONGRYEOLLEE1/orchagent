from typing import Literal
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langgraph.types import Command
from agent_core.builder import TeamBuilder
from agent_core.state import BaseAgentState
from agent_tools.file_io import (
    create_outline,
    read_document,
    write_document,
    edit_document,
    python_repl_tool,
)
from prompt_kit.prompts import (
    DOC_WRITER_PROMPT,
    NOTE_TAKER_PROMPT,
    CHART_GENERATOR_PROMPT,
)


class WritingTeamBuilder(TeamBuilder):
    def register_nodes(self):
        # 1. Document Writer
        doc_writer_agent = create_agent(
            model=self.llm,
            tools=[write_document, edit_document, read_document],
            system_prompt=DOC_WRITER_PROMPT.template,
        )

        def doc_writing_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
            result = doc_writer_agent.invoke(state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(
                            content=result["messages"][-1].content, name="doc_writer"
                        )
                    ]
                },
                goto="supervisor",
            )

        self.builder.add_node("doc_writer", doc_writing_node)

        # 2. Note Taker
        note_taking_agent = create_agent(
            model=self.llm,
            tools=[create_outline, read_document],
            system_prompt=NOTE_TAKER_PROMPT.template,
        )

        def note_taking_node(state: BaseAgentState) -> Command[Literal["supervisor"]]:
            result = note_taking_agent.invoke(state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(
                            content=result["messages"][-1].content, name="note_taker"
                        )
                    ]
                },
                goto="supervisor",
            )

        self.builder.add_node("note_taker", note_taking_node)

        # 3. Chart Generator
        chart_generating_agent = create_agent(
            model=self.llm,
            tools=[read_document, python_repl_tool],
            system_prompt=CHART_GENERATOR_PROMPT.template,
        )

        def chart_generating_node(
            state: BaseAgentState,
        ) -> Command[Literal["supervisor"]]:
            result = chart_generating_agent.invoke(state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(
                            content=result["messages"][-1].content,
                            name="chart_generator",
                        )
                    ]
                },
                goto="supervisor",
            )

        self.builder.add_node("chart_generator", chart_generating_node)


def get_writing_graph(llm):
    return WritingTeamBuilder(
        llm, "WritingTeam", ["doc_writer", "note_taker", "chart_generator"]
    ).build()
