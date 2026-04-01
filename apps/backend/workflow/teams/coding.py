from agent_core.builder import TeamBuilder
from agent_tools.coding import (
    apply_patch_edit,
    create_repo_file,
    git_diff,
    git_log,
    git_status,
    list_repo_tree,
    read_repo_file,
    run_repo_command,
    search_repo,
    verify_local_page,
)
from core.config import settings
from prompt_kit.prompts import (
    CODEBASE_EXPLORER_PROMPT,
    CODING_TEAM_SUPERVISOR_PROMPT,
    IMPLEMENTATION_ENGINEER_PROMPT,
    RUNTIME_VERIFIER_PROMPT,
)


class CodingTeamBuilder(TeamBuilder):
    def register_nodes(self):
        self.add_worker(
            "codebase_explorer",
            tools=[list_repo_tree, search_repo, read_repo_file, git_status, git_log],
            prompt=CODEBASE_EXPLORER_PROMPT.template,
        )
        self.add_worker(
            "implementation_engineer",
            tools=[
                list_repo_tree,
                search_repo,
                read_repo_file,
                apply_patch_edit,
                create_repo_file,
                run_repo_command,
                git_status,
                git_diff,
                git_log,
            ],
            prompt=IMPLEMENTATION_ENGINEER_PROMPT.template,
        )
        self.add_worker(
            "runtime_verifier",
            tools=[
                read_repo_file,
                run_repo_command,
                verify_local_page,
                git_status,
                git_diff,
            ],
            prompt=RUNTIME_VERIFIER_PROMPT.template,
        )


def get_coding_graph(llm):
    return CodingTeamBuilder(
        llm,
        "Coding Team",
        ["codebase_explorer", "implementation_engineer", "runtime_verifier"],
    ).build(
        with_validator=True,
        max_team_dispatches=settings.CODING_TEAM_MAX_DISPATCHES,
        system_prompt_template=CODING_TEAM_SUPERVISOR_PROMPT.template,
    )
