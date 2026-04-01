import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.repository_workspace_service import RepositoryWorkspaceService


class DummyDB:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)

    async def commit(self):
        return None

    async def refresh(self, item):
        if not getattr(item, "id", None):
            item.id = "workspace-job-1"


@pytest.mark.asyncio
async def test_create_workspace_for_turn_copies_bound_repository(monkeypatch, tmp_path):
    cache_root = tmp_path / "repo-cache"
    workspace_root = tmp_path / "workspaces"
    monkeypatch.setattr(
        "services.repository_workspace_service.settings.REPOSITORY_CACHE_DIR",
        str(cache_root),
    )
    monkeypatch.setattr(
        "services.repository_workspace_service.settings.REPOSITORY_WORKSPACE_DIR",
        str(workspace_root),
    )

    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    (source_repo / "app.py").write_text("print('hello')\n")
    subprocess.run(["git", "init"], cwd=source_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=source_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=source_repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "app.py"], cwd=source_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True, capture_output=True)

    binding = SimpleNamespace(
        id="binding-1",
        user_id="user-1",
        thread_id="thread-1",
        source_type="registered_repo",
        source_ref=str(source_repo),
        display_name="source-repo",
    )

    bundle = await RepositoryWorkspaceService.create_workspace_for_turn(
        DummyDB(),
        binding=binding,
        turn_id=uuid.uuid4(),
    )

    assert (bundle.repo_dir / "app.py").exists()
    assert bundle.log_dir.exists()
    assert bundle.artifact_dir.exists()

    (bundle.repo_dir / "app.py").write_text("print('updated')\n")
    summary = RepositoryWorkspaceService.summarize_workspace(bundle.repo_dir)
    assert summary["diff_available"] is True
    assert "app.py" in summary["changed_files"]
