import json
import pytest
from fastapi.testclient import TestClient
from main import app
from unittest.mock import MagicMock, AsyncMock
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from agent_core.state import build_route_entry
from services.trace_service import TraceService
from services.logging_service import LoggingService

client = TestClient(app)


class MockChunk:
    def __init__(self, content, additional_kwargs=None):
        self.content = content
        self.additional_kwargs = additional_kwargs or {}


class MockMessage:
    def __init__(self, content, name, type="ai"):
        self.content = content
        self.name = name
        self.type = type


def _sse_payloads(response):
    payloads = []
    for line in response.iter_lines():
        if line and line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    return payloads


@pytest.mark.asyncio
async def test_rope_algorithm_query_simulation(monkeypatch):
    """
    Simulate the 'RoPE Algorithm' query and verify that:
    1. Internal drafts are not leaked as 'text' events from supervisor.
    2. Tool activity counts are correct.
    3. Final answer is emitted once via finalizer.
    """

    # Mock Saver
    class MockSaver:
        async def setup(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aget_tuple(self, config):
            m = MagicMock()
            m.tasks = []
            return m

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda x: MockSaver())

    # Mock Graph that simulates the RoPE query workflow
    class MockRopeGraph:
        async def astream_events(self, inputs, config, version="v2"):
            # turn 1: Planner
            yield {
                "event": "on_chain_start",
                "name": "planner",
                "metadata": {"langgraph_node": "planner"},
            }
            yield {
                "event": "on_chain_end",
                "name": "planner",
                "metadata": {"langgraph_node": "planner"},
                "data": {
                    "output": Command(
                        update={"task_plan": "1. [research_team] Search RoPE."}
                    )
                },
            }

            # turn 2: Head Supervisor routes to Research
            yield {
                "event": "on_chain_start",
                "name": "head_supervisor",
                "metadata": {"langgraph_node": "head_supervisor"},
            }
            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "metadata": {"langgraph_node": "head_supervisor"},
                "data": {
                    "output": Command(
                        update={
                            "active_team": "research",
                            "streaming_status": "running",
                            "route_history": [
                                build_route_entry(
                                    layer="head",
                                    node="head_supervisor",
                                    next_node="research_team",
                                    team="research",
                                )
                            ],
                        }
                    )
                },
            }

            # turn 3: Research Team calls tools
            yield {
                "event": "on_tool_start",
                "name": "tavily_tool",
                "run_id": "t-1",
                "data": {"input": "RoPE algorithm explained"},
            }
            yield {
                "event": "on_tool_end",
                "name": "tavily_tool",
                "run_id": "t-1",
                "data": {"output": "RoPE is Rotary Positional Embedding..."},
            }

            yield {
                "event": "on_tool_start",
                "name": "scrape_webpages",
                "run_id": "t-2",
                "data": {"input": "url-1"},
            }
            yield {
                "event": "on_tool_end",
                "name": "scrape_webpages",
                "run_id": "t-2",
                "data": {"output": "Detailed math of RoPE..."},
            }

            # Research finishes
            yield {
                "event": "on_chain_end",
                "name": "research_team",
                "metadata": {"langgraph_node": "research_team"},
                "data": {
                    "output": Command(
                        update={
                            "route_history": [
                                build_route_entry(
                                    layer="team",
                                    node="supervisor",
                                    next_node="FINISH",
                                    team="research",
                                )
                            ]
                        }
                    )
                },
            }

            # turn 4: Head Supervisor sees research done, moves to finalizer
            # LLM follows new policy: content is EMPTY when returning FINISH for complex tasks
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "metadata": {"langgraph_node": "head_supervisor"},
                "data": {
                    "chunk": MockChunk(
                        content='{"reasoning": "Research complete. Delegating to finalizer.", "next": "FINISH", "content": ""}'
                    )
                },
                "run_id": "h-1",
            }

            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "metadata": {"langgraph_node": "head_supervisor"},
                "data": {
                    "output": Command(
                        update={
                            "active_team": None,
                            "streaming_status": "running",
                            "route_history": [
                                build_route_entry(
                                    layer="head",
                                    node="head_supervisor",
                                    next_node="finalizer",
                                )
                            ],
                        }
                    )
                },
            }

            # turn 5: Finalizer synthesizes
            final_json = (
                '{"content": "RoPE (Rotary Positional Embedding) is a method..."}'
            )
            for i in range(0, len(final_json), 5):
                chunk_str = final_json[i : i + 5]
                yield {
                    "event": "on_chat_model_stream",
                    "name": "ChatOpenAI",
                    "metadata": {"langgraph_node": "finalizer"},
                    "data": {"chunk": MockChunk(content=chunk_str)},
                    "run_id": "f-1",
                }

            yield {
                "event": "on_chain_end",
                "name": "finalizer",
                "metadata": {"langgraph_node": "finalizer"},
                "data": {
                    "output": Command(
                        update={
                            "streaming_status": "completed",
                            "messages": [
                                MockMessage(
                                    content="RoPE (Rotary Positional Embedding) is a method...",
                                    name="assistant",
                                )
                            ],
                            "route_history": [
                                build_route_entry(
                                    layer="head",
                                    node="finalizer",
                                    next_node="FINISH",
                                    status="completed",
                                )
                            ],
                        }
                    )
                },
            }

        async def aget_state(self, config, subgraphs=False):
            snapshot = MagicMock()
            snapshot.config = {"configurable": {"checkpoint_id": "cp-1"}}
            snapshot.values = {"messages": [], "route_history": []}
            snapshot.next = ()
            snapshot.created_at = "2026-03-18T00:00:00Z"
            return snapshot

    monkeypatch.setattr(
        "services.orchestration_service.OrchestrationService.get_graph",
        lambda: type(
            "B", (), {"compile": lambda self, checkpointer: MockRopeGraph()}
        )(),
    )
    persisted_batches = []

    async def mock_create_events(*args, **kwargs):
        persisted_batches.append(args[1])
        return args[1]

    monkeypatch.setattr(TraceService, "create_events", mock_create_events)
    monkeypatch.setattr(LoggingService, "log_message", AsyncMock())

    # Execution
    with client.stream(
        "POST",
        "/api/chat",
        json={"message": "RoPE 알고리즘 500자 답변", "thread_id": "rope-123"},
    ) as response:
        payloads = _sse_payloads(response)

    # Debug print
    for p in payloads:
        print(
            f"DEBUG: {p.get('event_type')} - {p.get('content') or p.get('status') or p.get('target') or p.get('display_name')}"
        )
        if p.get("event_type") == "error":
            print(f"ERROR MESSAGE: {p.get('message')}")

    # 1. Check Tool Count
    tool_starts = [p for p in payloads if p["event_type"] == "tool_start"]
    tool_ends = [p for p in payloads if p["event_type"] == "tool_end"]
    assert len(tool_starts) == 2
    assert len(tool_ends) == 2

    # 2. Check for LEAKED internal drafts
    text_events = [p for p in payloads if p["event_type"] == "text"]

    for te in text_events:
        assert "INTERNAL DRAFT" not in te["content"]
        assert "reasoning" not in te["content"]

    # 3. Check final answer presence
    final_text = "".join(te["content"] for te in text_events)
    assert "RoPE" in final_text
    assert "Rotary Positional Embedding" in final_text
    assert final_text == "RoPE (Rotary Positional Embedding) is a method..."

    # 4. Check completion status
    status_events = [p for p in payloads if p["event_type"] == "status"]
    assert any(s["status"] == "completed" for s in status_events)

    text_summaries = [
        event for event in persisted_batches[0] if event.event_type == "text_summary"
    ]
    assert len(text_summaries) == 1
    assert text_summaries[0].payload["content"] == final_text
