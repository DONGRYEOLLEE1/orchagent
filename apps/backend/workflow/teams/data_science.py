from agent_core.builder import TeamBuilder
from agent_tools.data import (
    extract_document_text,
    inspect_attachments,
    preview_tabular_file,
    profile_dataframe,
    python_repl_data_tool,
)
from core.config import settings
from prompt_kit.prompts import (
    DATA_ANALYST_PROMPT,
    DATA_ENGINEER_PROMPT,
    DATA_SCIENCE_TEAM_SUPERVISOR_PROMPT,
)


class DataScienceTeamBuilder(TeamBuilder):
    def register_nodes(self):
        self.add_worker(
            "data_engineer",
            tools=[
                inspect_attachments,
                preview_tabular_file,
                extract_document_text,
                profile_dataframe,
            ],
            prompt=DATA_ENGINEER_PROMPT.template,
        )
        self.add_worker(
            "data_analyst",
            tools=[
                inspect_attachments,
                preview_tabular_file,
                extract_document_text,
                profile_dataframe,
                python_repl_data_tool,
            ],
            prompt=DATA_ANALYST_PROMPT.template,
        )


def get_data_science_graph(llm):
    return DataScienceTeamBuilder(
        llm,
        "Data Science Team",
        ["data_engineer", "data_analyst"],
    ).build(
        with_validator=True,
        max_team_dispatches=settings.DATA_SCIENCE_TEAM_MAX_DISPATCHES,
        system_prompt_template=DATA_SCIENCE_TEAM_SUPERVISOR_PROMPT.template,
    )
