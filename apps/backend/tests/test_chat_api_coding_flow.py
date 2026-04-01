import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langgraph.types import Command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from main import app

client = TestClient(app)


def _sse_payloads(response):
    payloads = []
    for line in response.iter_lines():
        if line and line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    return payloads


def test_chat_stream_creates_repo_workspace_for_coding_request(monkeypatch, tmp_path):
    class MockSaver:
        async def setup(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", lambda _: MockSaver())

    created = {"called": False}

    async def fake_get_active_binding(db, *, thread_id, user_id):
        return SimpleNamespace(
            id="binding-1",
            thread_id=thread_id,
            user_id=user_id,
            source_type="git_url",
            source_ref="file:///tmp/sample-repo",
            display_name="sample-repo",
            default_branch=None,
            pinned_commit_sha=None,
            status="active",
            created_at=None,
            updated_at=None,
        )

    async def fake_create_workspace_for_turn(db, *, binding, turn_id):
        created["called"] = True
        repo_dir = tmp_path / "repo"
        artifact_dir = tmp_path / "artifacts"
        log_dir = tmp_path / "logs"
        repo_dir.mkdir()
        artifact_dir.mkdir()
        log_dir.mkdir()
        (repo_dir / "main.py").write_text("print('hello')\n")
        return SimpleNamespace(
            job=SimpleNamespace(id="workspace-job-1"),
            repo_dir=repo_dir,
            artifact_dir=artifact_dir,
            log_dir=log_dir,
        )

    async def fake_finalize_workspace_job(db, *, job_id, status):
        return None

    monkeypatch.setattr(
        "api.routes.chat.RepositoryBindingService.get_active_binding",
        fake_get_active_binding,
    )
    monkeypatch.setattr(
        "api.routes.chat.RepositoryWorkspaceService.create_workspace_for_turn",
        fake_create_workspace_for_turn,
    )
    monkeypatch.setattr(
        "api.routes.chat.RepositoryWorkspaceService.finalize_workspace_job",
        fake_finalize_workspace_job,
    )
    monkeypatch.setattr(
        "api.routes.chat.RepositoryWorkspaceService.summarize_workspace",
        lambda repo_dir: {"changed_files": [], "diff_available": False},
    )

    class Snapshot:
        config = {
            "configurable": {
                "thread_id": "thread-coding",
                "checkpoint_id": "cp-1",
                "checkpoint_ns": "",
            }
        }
        values = {
            "messages": ["a"],
            "route_history": [],
            "streaming_status": "completed",
        }
        next = ()
        created_at = "2026-03-31T00:00:00+00:00"

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_chain_end",
                "name": "head_supervisor",
                "data": {
                    "output": Command(
                        update={
                            "active_team": None,
                            "active_worker": None,
                            "streaming_status": "completed",
                            "route_history": [],
                        },
                        goto="__end__",
                    )
                },
            }

        async def aget_state(self, config, subgraphs=False):
            return Snapshot()

    monkeypatch.setattr(
        "api.routes.chat.get_orchagent_graph",
        lambda: type("Builder", (), {"compile": lambda self, checkpointer: MockGraph()})(),
    )

    with client.stream(
        "POST",
        "/api/chat",
        json={
            "message": "이 저장소에서 failing test를 고쳐줘",
            "thread_id": "thread-coding",
        },
    ) as response:
        payloads = _sse_payloads(response)

    assert response.status_code == 200
    assert created["called"] is True
    assert any(payload["event_type"] == "checkpoint" for payload in payloads)
