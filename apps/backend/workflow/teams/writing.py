from agent_core.builder import TeamBuilder
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
        self.add_worker(
            "doc_writer",
            tools=[write_document, edit_document, read_document],
            prompt=DOC_WRITER_PROMPT.template,
        )
        self.add_worker(
            "note_taker",
            tools=[create_outline, read_document],
            prompt=NOTE_TAKER_PROMPT.template,
        )
        self.add_worker(
            "chart_generator",
            tools=[read_document, python_repl_tool],
            prompt=CHART_GENERATOR_PROMPT.template,
        )


def get_writing_graph(llm):
    return WritingTeamBuilder(
        llm, "WritingTeam", ["doc_writer", "note_taker", "chart_generator"]
    ).build()
