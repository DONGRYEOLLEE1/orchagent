from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChangedFileEntry(BaseModel):
    path: str
    status: str | None = None  # "M"/"A"/"D"/"R"/"?" — free-form for now


class VerificationResult(BaseModel):
    kind: str  # "test" | "lint" | "build" | "runtime"
    label: str
    status: str  # "passed" | "failed" | "skipped" | "unverified"
    command: str | None = None
    summary: str | None = None


class FileEntry(BaseModel):
    """Shallow workspace tree entry surfaced to the UI."""

    path: str
    kind: Literal["file", "dir"]
    size_bytes: int | None = None
    changed_status: str | None = None  # "M"/"A"/"D"/"R"/"?"


class DiffSnippet(BaseModel):
    """Per-file slice of `git diff --unified=3 --no-color`, possibly truncated."""

    path: str
    unified_diff: str
    truncated: bool = False


class CodingSummary(BaseModel):
    """Typed projection of the last coding turn's workspace activity for a thread.

    Fields not yet captured by the backend (permission_mode, approval state, verification
    results, runtime verification, failure summary) default to None / empty — they will
    populate as plan Phase 1/5 land.
    """

    workspace_job_id: str | None = None
    repo_binding_id: str | None = None
    repo_commit_sha: str | None = None
    permission_mode: str | None = None
    approval_required: bool = False
    approval_state: str | None = None
    changed_files: list[ChangedFileEntry] = Field(default_factory=list)
    git_status: str | None = None
    diff_available: bool = False
    verification_results: list[VerificationResult] = Field(default_factory=list)
    failure_summary: str | None = None
    completed_at: datetime | None = None
    tree: list[FileEntry] = Field(default_factory=list)
    diffs: list[DiffSnippet] = Field(default_factory=list)

    @classmethod
    def from_turn_metadata(
        cls,
        metadata: dict[str, Any] | None,
        *,
        repo_commit_sha: str | None = None,
        completed_at: datetime | None = None,
    ) -> "CodingSummary | None":
        """Build a CodingSummary from a ChatTurn's metadata_json + associated WorkspaceJob."""
        if not metadata:
            return None
        workspace_summary = metadata.get("workspace_summary") or {}
        job_id = metadata.get("workspace_job_id")
        binding_id = metadata.get("repo_binding_id")
        if not workspace_summary and not job_id and not binding_id:
            return None
        raw_changed = workspace_summary.get("changed_files") or []
        changed_files: list[ChangedFileEntry] = []
        for entry in raw_changed:
            if isinstance(entry, str):
                changed_files.append(ChangedFileEntry(path=entry))
            elif isinstance(entry, dict) and entry.get("path"):
                changed_files.append(
                    ChangedFileEntry(path=str(entry["path"]), status=entry.get("status"))
                )
        raw_tree = workspace_summary.get("tree") or []
        tree: list[FileEntry] = []
        for entry in raw_tree:
            if isinstance(entry, dict) and entry.get("path") and entry.get("kind"):
                try:
                    tree.append(FileEntry(**entry))
                except Exception:
                    continue
        raw_diffs = workspace_summary.get("diffs") or []
        diffs: list[DiffSnippet] = []
        for entry in raw_diffs:
            if isinstance(entry, dict) and entry.get("path") and "unified_diff" in entry:
                try:
                    diffs.append(DiffSnippet(**entry))
                except Exception:
                    continue
        return cls(
            workspace_job_id=job_id,
            repo_binding_id=binding_id,
            repo_commit_sha=repo_commit_sha,
            changed_files=changed_files,
            git_status=workspace_summary.get("git_status"),
            diff_available=bool(workspace_summary.get("diff_available", False)),
            completed_at=completed_at,
            tree=tree,
            diffs=diffs,
        )
