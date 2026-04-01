from __future__ import annotations

import mimetypes
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ToolAttachment:
    id: str
    kind: str
    file_name: str
    mime_type: str
    size_bytes: int | None
    storage_path: str


@dataclass(slots=True)
class ToolArtifact:
    kind: str
    file_name: str
    mime_type: str
    size_bytes: int | None
    storage_path: str
    title: str | None = None


@dataclass(slots=True)
class ToolRuntimeContext:
    thread_id: str
    user_id: str
    attachments: dict[str, ToolAttachment]
    workspace_dir: Path
    artifact_dir: Path
    log_dir: Path | None = None
    registered_artifacts: list[ToolArtifact] = field(default_factory=list)


_runtime_context: ContextVar[ToolRuntimeContext | None] = ContextVar(
    "agent_tool_runtime_context",
    default=None,
)


def set_tool_runtime_context(context: ToolRuntimeContext) -> Token:
    context.workspace_dir.mkdir(parents=True, exist_ok=True)
    context.artifact_dir.mkdir(parents=True, exist_ok=True)
    if context.log_dir is not None:
        context.log_dir.mkdir(parents=True, exist_ok=True)
    return _runtime_context.set(context)


def reset_tool_runtime_context(token: Token) -> None:
    _runtime_context.reset(token)


def get_tool_runtime_context() -> ToolRuntimeContext:
    context = _runtime_context.get()
    if context is None:
        raise RuntimeError("Tool runtime context is not configured for this turn.")
    return context


def list_runtime_attachments() -> list[ToolAttachment]:
    return list(get_tool_runtime_context().attachments.values())


def resolve_runtime_attachment(attachment_id: str) -> ToolAttachment:
    context = get_tool_runtime_context()
    attachment = context.attachments.get(str(attachment_id))
    if attachment is None:
        raise ValueError(f"Attachment {attachment_id} is not available in this turn.")
    return attachment


def artifact_path(file_name: str) -> Path:
    context = get_tool_runtime_context()
    return context.artifact_dir / Path(file_name).name


def register_runtime_artifact(
    *,
    file_path: str | Path,
    title: str | None = None,
    kind: str = "artifact",
    mime_type: str | None = None,
) -> ToolArtifact:
    context = get_tool_runtime_context()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate_name = candidate.name
        search_matches = [
            *context.artifact_dir.rglob(candidate_name),
            *context.workspace_dir.rglob(candidate_name),
        ]
        existing_search_match = next(
            (match.resolve() for match in search_matches if match.exists()),
            None,
        )
        cwd_candidate = (Path.cwd() / candidate).resolve()
        artifact_candidate = (context.artifact_dir / candidate).resolve()
        workspace_candidate = (context.workspace_dir / candidate).resolve()
        existing_candidate = next(
            (
                option
                for option in (
                    existing_search_match,
                    cwd_candidate,
                    artifact_candidate,
                    workspace_candidate,
                )
                if option is not None and option.exists()
            ),
            artifact_candidate,
        )
        candidate = existing_candidate
    else:
        candidate = candidate.resolve()

    allowed_roots = [context.workspace_dir.resolve(), context.artifact_dir.resolve()]
    if context.log_dir is not None:
        allowed_roots.append(context.log_dir.resolve())
    if not any(str(candidate).startswith(str(root)) for root in allowed_roots):
        raise ValueError("Artifacts must be stored within the analysis workspace.")
    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"Artifact file not found: {candidate}")

    resolved_mime = mime_type or mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    artifact = ToolArtifact(
        kind=kind,
        file_name=candidate.name,
        mime_type=resolved_mime,
        size_bytes=candidate.stat().st_size,
        storage_path=str(candidate),
        title=title,
    )
    if artifact.storage_path not in {item.storage_path for item in context.registered_artifacts}:
        context.registered_artifacts.append(artifact)
    return artifact


def collect_runtime_artifacts() -> list[ToolArtifact]:
    return list(get_tool_runtime_context().registered_artifacts)


def attachment_manifest() -> list[dict[str, Any]]:
    return [
        {
            "id": attachment.id,
            "kind": attachment.kind,
            "file_name": attachment.file_name,
            "mime_type": attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "storage_path": attachment.storage_path,
        }
        for attachment in list_runtime_attachments()
    ]
