from agent_core.builder import TeamBuilder
from langchain_core.tools import tool


class DummyChatModel:
    pass


class DummyTeamBuilder(TeamBuilder):
    def register_nodes(self):
        @tool
        def tool_a():
            "A"

        @tool
        def tool_b():
            "B"

        self.add_worker("worker_a", tools=[tool_a, tool_b], prompt="prompt")


def test_worker_registration_uses_concrete_chat_model(monkeypatch):
    captured = {}

    def fake_create_agent(
        *, model, tools=None, system_prompt=None, state_schema=None, name=None, **kwargs
    ):
        captured["model"] = model
        captured["tools"] = tools
        captured["name"] = name
        return lambda state: {}

    monkeypatch.setattr("agent_core.builder.create_agent", fake_create_agent)

    llm = DummyChatModel()
    DummyTeamBuilder(llm, "DummyTeam", ["worker_a"]).build()  # type: ignore

    assert captured["model"] is llm
    assert captured["name"] == "worker_a"
    assert len(captured["tools"]) == 2
