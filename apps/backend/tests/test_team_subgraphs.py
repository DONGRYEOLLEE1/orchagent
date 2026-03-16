from pathlib import Path

import pytest

from agent_core.builder import TeamBuilder
from agent_core.state import BaseAgentState


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
