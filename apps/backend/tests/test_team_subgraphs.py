from pathlib import Path

import pytest

from agent_core.builder import TeamBuilder
from agent_core.state import BaseAgentState
from workflow.teams.research import ResearchTeamBuilder, get_research_graph
from workflow.teams.coding import CodingTeamBuilder, get_coding_graph
from workflow.teams.writing import get_writing_graph
from prompt_kit.prompts import (
    CODEBASE_EXPLORER_PROMPT,
    CODING_TEAM_SUPERVISOR_PROMPT,
    IMPLEMENTATION_ENGINEER_PROMPT,
    RESEARCH_TEAM_SUPERVISOR_PROMPT,
    RUNTIME_VERIFIER_PROMPT,
    SEARCH_WORKER_PROMPT,
    WEB_SCRAPER_PROMPT,
)


class DummyTeamBuilder(TeamBuilder):
    def register_nodes(self):
        self.add_worker("worker_a", tools=[], prompt="worker a prompt")
        self.add_worker("worker_b", tools=[], prompt="worker b prompt")


def test_team_builder_registers_native_worker_subgraphs(monkeypatch):
    created = []

    def fake_create_agent(
        *, model, tools=None, system_prompt=None, state_schema=None, name=None, **kwargs
    ):
        created.append(
            {
                "name": name,
                "system_prompt": system_prompt,
                "state_schema": state_schema,
            }
        )
        return lambda state: {}

    monkeypatch.setattr("agent_core.builder.create_agent", fake_create_agent)

    graph = DummyTeamBuilder(object(), "DummyTeam", ["worker_a", "worker_b"]).build()  # type: ignore
    edges = set(graph.builder.edges)

    assert [entry["name"] for entry in created] == ["worker_a", "worker_b"]
    assert all(entry["state_schema"] is BaseAgentState for entry in created)
    assert "worker_a" in graph.nodes
    assert "worker_b" in graph.nodes
    assert ("worker_a", "supervisor") in edges
    assert ("worker_b", "supervisor") in edges


def test_research_team_builder_uses_split_worker_prompts(monkeypatch):
    created = []

    def fake_create_agent(
        *, model, tools=None, system_prompt=None, state_schema=None, name=None, **kwargs
    ):
        created.append(
            {
                "name": name,
                "system_prompt": system_prompt,
            }
        )
        return lambda state: {}

    monkeypatch.setattr("agent_core.builder.create_agent", fake_create_agent)

    builder = ResearchTeamBuilder(object(), "ResearchTeam", ["search", "web_scraper"])  # type: ignore[arg-type]
    builder.register_nodes()

    assert created == [
        {
            "name": "search",
            "system_prompt": SEARCH_WORKER_PROMPT.template,
        },
        {
            "name": "web_scraper",
            "system_prompt": WEB_SCRAPER_PROMPT.template,
        },
    ]


def test_coding_team_builder_uses_worker_specific_prompts(monkeypatch):
    created = []

    def fake_create_agent(
        *, model, tools=None, system_prompt=None, state_schema=None, name=None, **kwargs
    ):
        created.append({"name": name, "system_prompt": system_prompt})
        return lambda state: {}

    monkeypatch.setattr("agent_core.builder.create_agent", fake_create_agent)

    builder = CodingTeamBuilder(
        object(),
        "Coding Team",
        ["codebase_explorer", "implementation_engineer", "runtime_verifier"],
    )  # type: ignore[arg-type]
    builder.register_nodes()

    assert created == [
        {"name": "codebase_explorer", "system_prompt": CODEBASE_EXPLORER_PROMPT.template},
        {"name": "implementation_engineer", "system_prompt": IMPLEMENTATION_ENGINEER_PROMPT.template},
        {"name": "runtime_verifier", "system_prompt": RUNTIME_VERIFIER_PROMPT.template},
    ]


@pytest.mark.parametrize(
    ("relative_path", "worker_count"),
    [
        ("apps/backend/workflow/teams/research.py", 2),
        ("apps/backend/workflow/teams/writing.py", 3),
        ("apps/backend/workflow/teams/vision.py", 1),
    ],
)
def test_team_modules_use_add_worker_without_blocking_wrappers(
    relative_path: str, worker_count: int
):
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / relative_path).read_text()

    assert source.count("self.add_worker(") == worker_count
    assert ".invoke(state)" not in source
    assert "HumanMessage(" not in source
    assert "create_agent(" not in source


@pytest.mark.parametrize(
    ("builder_path", "settings_path", "configured_limit", "factory"),
    [
        (
            "workflow.teams.research.ResearchTeamBuilder.build",
            "workflow.teams.research.settings.RESEARCH_TEAM_MAX_DISPATCHES",
            7,
            get_research_graph,
        ),
        (
            "workflow.teams.writing.WritingTeamBuilder.build",
            "workflow.teams.writing.settings.WRITING_TEAM_MAX_DISPATCHES",
            11,
            get_writing_graph,
        ),
        (
            "workflow.teams.coding.CodingTeamBuilder.build",
            "workflow.teams.coding.settings.CODING_TEAM_MAX_DISPATCHES",
            13,
            get_coding_graph,
        ),
    ],
)
def test_team_graphs_use_configured_dispatch_limits(
    monkeypatch, builder_path: str, settings_path: str, configured_limit: int, factory
):
    captured: dict[str, object] = {}

    def fake_build(
        self,
        with_validator=False,
        max_team_dispatches=None,
        system_prompt_template=None,
    ):
        captured["with_validator"] = with_validator
        captured["max_team_dispatches"] = max_team_dispatches
        captured["system_prompt_template"] = system_prompt_template
        return "compiled-graph"

    monkeypatch.setattr(builder_path, fake_build)
    monkeypatch.setattr(settings_path, configured_limit)

    assert factory(object()) == "compiled-graph"
    expected = {
        "with_validator": True,
        "max_team_dispatches": configured_limit,
        "system_prompt_template": None,
    }
    if "research" in builder_path:
        expected["system_prompt_template"] = RESEARCH_TEAM_SUPERVISOR_PROMPT.template
    if "coding" in builder_path:
        expected["system_prompt_template"] = CODING_TEAM_SUPERVISOR_PROMPT.template
    assert captured == expected


def test_research_team_supervisor_prompt_encodes_search_then_scrape_order():
    prompt = RESEARCH_TEAM_SUPERVISOR_PROMPT.template

    assert "Start with `search`" in prompt
    assert "Use `web_scraper` only after `search`" in prompt
    assert "Do not call `web_scraper` first" in prompt
