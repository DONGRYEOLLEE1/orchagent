import pytest

from agent_tools.coding import (
    apply_patch_edit,
    create_repo_file,
    read_repo_file,
    run_repo_command,
    search_repo,
)
from agent_tools.runtime import ToolRuntimeContext, reset_tool_runtime_context, set_tool_runtime_context


@pytest.fixture
def coding_runtime_context(tmp_path):
    repo_dir = tmp_path / "repo"
    artifact_dir = tmp_path / "artifacts"
    log_dir = tmp_path / "logs"
    repo_dir.mkdir()
    artifact_dir.mkdir()
    log_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')\n")

    token = set_tool_runtime_context(
        ToolRuntimeContext(
            thread_id="thread-coding",
            user_id="user-1",
            attachments={},
            workspace_dir=repo_dir,
            artifact_dir=artifact_dir,
            log_dir=log_dir,
        )
    )
    try:
        yield repo_dir, artifact_dir, log_dir
    finally:
        reset_tool_runtime_context(token)


def test_coding_tools_read_edit_and_execute(coding_runtime_context):
    repo_dir, _artifact_dir, log_dir = coding_runtime_context

    read_output = read_repo_file.invoke({"file_path": "main.py"})
    assert "print('hello')" in read_output

    search_output = search_repo.invoke({"query": "hello"})
    assert "main.py" in search_output

    edit_output = apply_patch_edit.invoke(
        {
            "file_path": "main.py",
            "old_text": "print('hello')\n",
            "new_text": "print('updated')\n",
        }
    )
    assert edit_output["success"] is True
    assert "updated" in (repo_dir / "main.py").read_text()

    create_output = create_repo_file.invoke(
        {"file_path": "notes.txt", "content": "done\n"}
    )
    assert create_output["success"] is True
    assert (repo_dir / "notes.txt").exists()

    command_output = run_repo_command.invoke({"command": "python -c \"print('ok')\""})
    assert command_output["success"] is True
    assert "ok" in command_output["stdout"]
    assert any(log_dir.iterdir())


def test_coding_tools_keep_paths_inside_workspace(coding_runtime_context):
    with pytest.raises(ValueError):
        read_repo_file.invoke({"file_path": "../outside.txt"})
