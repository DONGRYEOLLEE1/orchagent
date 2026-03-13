from typing import cast
from agent_core.builder import TeamBuilder
from agent_core.state import BaseAgentState
from langchain_core.tools import tool


class DummyChatModel:
    def __init__(self, bound_tools=None):
        self.bound_tools = bound_tools or []

    def bind_tools(self, tools):
        return DummyChatModel(tools)


class DummyTeamBuilder(TeamBuilder):
    def register_nodes(self):
        @tool
        def tool_a():
            "A"

        @tool
        def tool_b():
            "B"

        self.add_worker("worker_a", tools=[tool_a, tool_b], prompt="prompt")


def test_dynamic_tools_binding(monkeypatch):
    captured_model = []

    def fake_create_react_agent(*, model, tools, prompt, state_schema, version, name):
        captured_model.append(model)
        return lambda state: {}

    monkeypatch.setattr(
        "agent_core.builder.create_react_agent", fake_create_react_agent
    )

    llm = DummyChatModel()
    DummyTeamBuilder(llm, "DummyTeam", ["worker_a"]).build()  # type: ignore

    dynamic_model = captured_model[0]

    # Test state with no restrictions
    state1 = cast(BaseAgentState, {"messages": [], "next": ""})
    model1 = dynamic_model(state1, None)
    assert len(model1.bound_tools) == 2

    # Test state with restriction
    state2 = cast(
        BaseAgentState, {"messages": [], "next": "", "active_tools": ["tool_a"]}
    )
    model2 = dynamic_model(state2, None)
    assert len(model2.bound_tools) == 1
    assert (
        getattr(
            model2.bound_tools[0],
            "name",
            getattr(model2.bound_tools[0], "__name__", str(model2.bound_tools[0])),
        )
        == "tool_a"
    )
