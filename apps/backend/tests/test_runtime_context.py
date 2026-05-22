"""Phase 4.2 — runtime context unit tests.

The runtime context module (``packages/agent-tools/src/agent_tools/runtime.py``)
underpins every worker tool but only had implicit coverage through the
high-level integration tests. These tests pin the contract directly so
later phases can refactor with confidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_tools.runtime import (
    ToolArtifact,
    ToolAttachment,
    ToolRuntimeContext,
    attachment_manifest,
    collect_runtime_artifacts,
    get_tool_runtime_context,
    list_runtime_attachments,
    register_runtime_artifact,
    reset_tool_runtime_context,
    resolve_runtime_attachment,
    set_tool_runtime_context,
)


@pytest.fixture()
def runtime(tmp_path: Path):
    context = ToolRuntimeContext(
        thread_id="thread-1",
        user_id="user-1",
        attachments={
            "att-1": ToolAttachment(
                id="att-1",
                kind="image",
                file_name="hello.png",
                mime_type="image/png",
                size_bytes=12,
                storage_path=str(tmp_path / "hello.png"),
            )
        },
        workspace_dir=tmp_path / "workspace",
        artifact_dir=tmp_path / "artifacts",
    )
    token = set_tool_runtime_context(context)
    try:
        yield context
    finally:
        reset_tool_runtime_context(token)


def test_get_tool_runtime_context_raises_outside_token() -> None:
    """No active runtime → get_tool_runtime_context() must raise. The positive
    "returns active context" half is implicitly covered by every fixture-using
    test below."""
    with pytest.raises(RuntimeError):
        get_tool_runtime_context()


def test_set_tool_runtime_context_creates_directories(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace_a"
    artifact_dir = tmp_path / "artifacts_a"
    log_dir = tmp_path / "logs_a"
    context = ToolRuntimeContext(
        thread_id="t",
        user_id="u",
        attachments={},
        workspace_dir=workspace_dir,
        artifact_dir=artifact_dir,
        log_dir=log_dir,
    )
    token = set_tool_runtime_context(context)
    try:
        assert workspace_dir.is_dir()
        assert artifact_dir.is_dir()
        assert log_dir.is_dir()
    finally:
        reset_tool_runtime_context(token)


def test_attachment_manifest_and_resolve(runtime) -> None:
    """Manifest exposes attachments; resolve on unknown id raises."""
    items = attachment_manifest()
    assert len(items) == 1
    assert items[0]["id"] == "att-1"
    assert items[0]["mime_type"] == "image/png"
    assert [att.id for att in list_runtime_attachments()] == ["att-1"]
    with pytest.raises(ValueError):
        resolve_runtime_attachment("missing")


def test_register_runtime_artifact_appends_and_dedupes(runtime) -> None:
    """Identical artifact paths must be collapsed into a single entry."""
    runtime.artifact_dir.mkdir(parents=True, exist_ok=True)
    csv_path = runtime.artifact_dir / "report.csv"
    csv_path.write_text("a,b,c", encoding="utf-8")

    first = register_runtime_artifact(file_path=csv_path, title="Report", kind="table")
    second = register_runtime_artifact(file_path=csv_path, title="Report", kind="table")

    assert isinstance(first, ToolArtifact)
    assert isinstance(second, ToolArtifact)
    artifacts = collect_runtime_artifacts()
    assert sum(1 for art in artifacts if art.storage_path == str(csv_path)) == 1


def test_register_runtime_artifact_rejects_outside_workspace_or_missing(
    runtime, tmp_path: Path
) -> None:
    """Artifacts must stay inside the artifact_dir and must exist on disk."""
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError):
        register_runtime_artifact(file_path=outside)

    with pytest.raises(ValueError):
        register_runtime_artifact(file_path=runtime.artifact_dir / "missing.bin")
