from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import AsyncSessionLocal
from models.analytics import ChatTurn
from models.repository import ThreadRepositoryBinding, WorkspaceJob
from models.logging import KST
from schemas.coding import CodingSummary


BACKEND_APP_ROOT = Path(__file__).resolve().parents[1]

# Caps for the coding_summary payload that ships through SSE + turn metadata JSONB.
WORKSPACE_SUMMARY_MAX_BYTES = 128 * 1024
_TREE_DEPTH = 2
_TREE_MAX_ENTRIES = 200
_DIFF_MAX_FILES = 20
_DIFF_PER_FILE_BYTES = 4 * 1024
_TREE_EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".pdf", ".zip", ".gz", ".tar", ".bz2", ".7z",
    ".mp3", ".mp4", ".mov", ".wav", ".flac",
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".woff", ".woff2", ".ttf", ".otf",
}


def _resolve_root(configured_path: str) -> Path:
    candidate = Path(configured_path)
    if not candidate.is_absolute():
        candidate = (BACKEND_APP_ROOT / candidate).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _now_kst() -> datetime:
    return datetime.now(KST)


def _run_checked(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Required binary not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or f"Command failed: {' '.join(args)}"
        raise HTTPException(status_code=400, detail=detail) from exc


def _detect_repo_root(extracted_root: Path) -> Path:
    children = [child for child in extracted_root.iterdir()]
    if not children:
        raise HTTPException(status_code=400, detail="Repository archive is empty")

    directories = [child for child in children if child.is_dir()]
    files = [child for child in children if child.is_file()]
    if len(directories) == 1 and not files:
        return directories[0]
    return extracted_root


@dataclass(slots=True)
class MaterializedRepository:
    cache_root: Path
    repo_root: Path
    repo_commit_sha: str | None


@dataclass(slots=True)
class WorkspaceBundle:
    job: WorkspaceJob
    repo_dir: Path
    artifact_dir: Path
    log_dir: Path
    repo_commit_sha: str | None


class RepositoryWorkspaceService:
    @staticmethod
    def cache_root() -> Path:
        return _resolve_root(settings.REPOSITORY_CACHE_DIR)

    @staticmethod
    def workspace_root() -> Path:
        return _resolve_root(settings.REPOSITORY_WORKSPACE_DIR)

    @staticmethod
    def binding_cache_root(binding_id: str) -> Path:
        root = RepositoryWorkspaceService.cache_root() / f"binding_{binding_id}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _binding_manifest_path(binding_id: str) -> Path:
        return RepositoryWorkspaceService.binding_cache_root(binding_id) / "manifest.json"

    @staticmethod
    def _read_binding_manifest(binding_id: str) -> dict | None:
        manifest_path = RepositoryWorkspaceService._binding_manifest_path(binding_id)
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text())
        except Exception:
            return None

    @staticmethod
    def _write_binding_manifest(binding: ThreadRepositoryBinding) -> None:
        manifest_path = RepositoryWorkspaceService._binding_manifest_path(binding.id)
        manifest_path.write_text(
            json.dumps(
                {
                    "source_type": binding.source_type,
                    "source_ref": binding.source_ref,
                    "display_name": binding.display_name,
                }
            )
        )

    @staticmethod
    def _clone_repo(source_ref: str, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        _run_checked(["git", "clone", "--depth", "1", source_ref, str(destination)])

    @staticmethod
    def _copy_registered_repo(source_ref: str, destination: Path) -> None:
        source_path = Path(source_ref).expanduser()
        if not source_path.is_absolute():
            source_path = source_path.resolve()
        if not source_path.exists() or not source_path.is_dir():
            raise HTTPException(status_code=400, detail="Registered repository path was not found")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_path, destination)

    @staticmethod
    def _extract_zip(source_ref: str, destination: Path) -> Path:
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(source_ref) as archive:
                archive.extractall(destination)
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Invalid repository zip archive") from exc
        return _detect_repo_root(destination)

    @staticmethod
    def _repo_commit_sha(repo_root: Path) -> str | None:
        if not (repo_root / ".git").exists():
            return None
        result = _run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
        return (result.stdout or "").strip() or None

    @staticmethod
    def _materialize_source(binding: ThreadRepositoryBinding) -> MaterializedRepository:
        cache_root = RepositoryWorkspaceService.binding_cache_root(binding.id)
        repo_root = cache_root / "source"
        current_manifest = RepositoryWorkspaceService._read_binding_manifest(binding.id)
        expected_manifest = {
            "source_type": binding.source_type,
            "source_ref": binding.source_ref,
            "display_name": binding.display_name,
        }

        if current_manifest != expected_manifest or not repo_root.exists():
            if repo_root.exists():
                shutil.rmtree(repo_root)
            if binding.source_type in {"github_url", "git_url"}:
                RepositoryWorkspaceService._clone_repo(binding.source_ref, repo_root)
            elif binding.source_type == "repo_zip":
                repo_root = RepositoryWorkspaceService._extract_zip(binding.source_ref, repo_root)
            elif binding.source_type == "registered_repo":
                RepositoryWorkspaceService._copy_registered_repo(binding.source_ref, repo_root)
            else:
                raise HTTPException(status_code=400, detail="Unsupported repository binding source")
            RepositoryWorkspaceService._write_binding_manifest(binding)
        elif binding.source_type == "repo_zip":
            repo_root = _detect_repo_root(repo_root)

        return MaterializedRepository(
            cache_root=cache_root,
            repo_root=repo_root,
            repo_commit_sha=RepositoryWorkspaceService._repo_commit_sha(repo_root),
        )

    @staticmethod
    async def materialize_binding(
        db: AsyncSession,
        *,
        binding: ThreadRepositoryBinding,
    ) -> MaterializedRepository:
        del db
        return await asyncio.to_thread(
            RepositoryWorkspaceService._materialize_source, binding
        )

    @staticmethod
    def _prepare_workspace_dirs(
        materialized: MaterializedRepository, job_root: Path
    ) -> tuple[Path, Path, Path]:
        if job_root.exists():
            shutil.rmtree(job_root)
        repo_dir = job_root / "repo"
        artifact_dir = job_root / "artifacts"
        log_dir = job_root / "logs"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(materialized.repo_root, repo_dir)
        return repo_dir, artifact_dir, log_dir

    @staticmethod
    async def create_workspace_for_turn(
        db: AsyncSession,
        *,
        binding: ThreadRepositoryBinding,
        turn_id,
    ) -> WorkspaceBundle:
        materialized = await asyncio.to_thread(
            RepositoryWorkspaceService._materialize_source, binding
        )
        job_root = (
            RepositoryWorkspaceService.workspace_root()
            / f"user_{binding.user_id}"
            / f"thread_{binding.thread_id}"
            / f"turn_{turn_id}"
        )
        repo_dir, artifact_dir, log_dir = await asyncio.to_thread(
            RepositoryWorkspaceService._prepare_workspace_dirs, materialized, job_root
        )

        job = WorkspaceJob(
            thread_id=binding.thread_id,
            turn_id=turn_id,
            binding_id=binding.id,
            workspace_path=str(repo_dir),
            artifact_path=str(artifact_dir),
            log_path=str(log_dir),
            repo_commit_sha=materialized.repo_commit_sha,
            status="running",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        return WorkspaceBundle(
            job=job,
            repo_dir=repo_dir,
            artifact_dir=artifact_dir,
            log_dir=log_dir,
            repo_commit_sha=materialized.repo_commit_sha,
        )

    @staticmethod
    def _build_tree_entries(repo_dir: Path, changed_map: dict[str, str]) -> list[dict]:
        """Depth-limited scan of the workspace root surfacing file/dir entries.

        Binary files by extension and well-known noise dirs are skipped. Changed files
        inherit their status from `changed_map` so the UI can colour them consistently.
        """
        entries: list[dict] = []

        def _walk(base: Path, depth: int) -> None:
            if depth > _TREE_DEPTH or len(entries) >= _TREE_MAX_ENTRIES:
                return
            try:
                children = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except OSError:
                return
            for child in children:
                if len(entries) >= _TREE_MAX_ENTRIES:
                    return
                name = child.name
                if child.is_dir():
                    if name in _TREE_EXCLUDED_DIRS:
                        continue
                    rel = child.relative_to(repo_dir).as_posix()
                    entries.append({"path": rel, "kind": "dir"})
                    _walk(child, depth + 1)
                    continue
                if name.startswith("."):
                    continue
                if child.suffix.lower() in _BINARY_SUFFIXES:
                    continue
                try:
                    size_bytes = child.stat().st_size
                except OSError:
                    size_bytes = None
                rel = child.relative_to(repo_dir).as_posix()
                entries.append(
                    {
                        "path": rel,
                        "kind": "file",
                        "size_bytes": size_bytes,
                        "changed_status": changed_map.get(rel),
                    }
                )

        _walk(repo_dir, 0)
        return entries

    @staticmethod
    def _parse_unified_diff(raw_diff: str) -> list[dict]:
        """Split a single `git diff --unified=3 --no-color` blob into per-file snippets.

        Keeps at most `_DIFF_MAX_FILES` files and truncates each body to
        `_DIFF_PER_FILE_BYTES` so the SSE/JSONB payload stays bounded.
        """
        if not raw_diff:
            return []
        snippets: list[dict] = []
        current_path: str | None = None
        current_lines: list[str] = []

        def _flush() -> None:
            nonlocal current_path, current_lines
            if current_path is None:
                current_lines = []
                return
            body = "\n".join(current_lines)
            truncated = False
            if len(body.encode("utf-8", errors="ignore")) > _DIFF_PER_FILE_BYTES:
                body = body[:_DIFF_PER_FILE_BYTES]
                truncated = True
            snippets.append(
                {
                    "path": current_path,
                    "unified_diff": body,
                    "truncated": truncated,
                }
            )
            current_path = None
            current_lines = []

        for line in raw_diff.splitlines():
            if line.startswith("diff --git "):
                _flush()
                if len(snippets) >= _DIFF_MAX_FILES:
                    return snippets
                # `diff --git a/<path> b/<path>` — prefer b/<path>
                parts = line.split(" b/", 1)
                if len(parts) == 2:
                    current_path = parts[1].strip()
                else:
                    current_path = line.replace("diff --git ", "").strip()
                current_lines = [line]
            else:
                if current_path is not None:
                    current_lines.append(line)
        _flush()
        return snippets

    @staticmethod
    def _enforce_payload_budget(payload: dict) -> dict:
        """Drop diffs from the tail until the serialized payload fits the soft cap."""
        try:
            serialized = json.dumps(payload, ensure_ascii=False)
        except Exception:
            return payload
        if len(serialized.encode("utf-8", errors="ignore")) <= WORKSPACE_SUMMARY_MAX_BYTES:
            return payload
        diffs = payload.get("diffs") or []
        while diffs and len(json.dumps(payload, ensure_ascii=False).encode("utf-8", errors="ignore")) > WORKSPACE_SUMMARY_MAX_BYTES:
            diffs.pop()
        payload["diffs"] = diffs
        return payload

    @staticmethod
    def _summarize_workspace_sync(repo_dir: Path) -> dict[str, object]:
        if not (repo_dir / ".git").exists():
            return {
                "changed_files": [],
                "diff_available": False,
                "tree": [],
                "diffs": [],
            }

        status_result = _run_checked(["git", "status", "--short"], cwd=repo_dir)
        diff_name_only = _run_checked(["git", "diff", "--name-only"], cwd=repo_dir)
        full_diff = _run_checked(
            ["git", "diff", "--unified=3", "--no-color"], cwd=repo_dir
        )

        changed_files_list = [
            line.strip()
            for line in (diff_name_only.stdout or "").splitlines()
            if line.strip()
        ]

        # Derive a path -> status map from `git status --short` (porcelain line format).
        changed_map: dict[str, str] = {}
        for line in (status_result.stdout or "").splitlines():
            if len(line) < 3:
                continue
            status_code = line[:2].strip() or "?"
            path = line[3:].strip()
            if path:
                changed_map[path] = status_code[:1] or status_code

        tree_entries = RepositoryWorkspaceService._build_tree_entries(repo_dir, changed_map)
        diff_entries = RepositoryWorkspaceService._parse_unified_diff(
            full_diff.stdout or ""
        )

        payload: dict[str, object] = {
            "changed_files": changed_files_list,
            "git_status": (status_result.stdout or "").strip(),
            "diff_available": True,
            "tree": tree_entries,
            "diffs": diff_entries,
        }
        return RepositoryWorkspaceService._enforce_payload_budget(payload)

    @staticmethod
    async def summarize_workspace(repo_dir: Path) -> dict[str, object]:
        return await asyncio.to_thread(
            RepositoryWorkspaceService._summarize_workspace_sync, repo_dir
        )

    @staticmethod
    async def get_latest_coding_summary(
        db: AsyncSession, *, thread_id: str
    ) -> CodingSummary | None:
        """Return the typed coding summary for the most recent workspace job on a thread.

        Joins the latest WorkspaceJob for the thread with its ChatTurn metadata so the UI
        can hydrate historical coding turns without replaying the whole trace.
        """
        job_stmt = (
            select(WorkspaceJob)
            .where(WorkspaceJob.thread_id == thread_id)
            .order_by(WorkspaceJob.created_at.desc())
            .limit(1)
        )
        job = (await db.execute(job_stmt)).scalar_one_or_none()
        if job is None:
            return None

        turn_stmt = select(ChatTurn).where(ChatTurn.id == job.turn_id)
        turn = (await db.execute(turn_stmt)).scalar_one_or_none()
        metadata = turn.metadata_json if turn is not None else None
        return CodingSummary.from_turn_metadata(
            metadata,
            repo_commit_sha=job.repo_commit_sha,
            completed_at=job.completed_at,
        )

    @staticmethod
    async def finalize_workspace_job(
        db: AsyncSession,
        *,
        job_id: str,
        status: str,
    ) -> WorkspaceJob | None:
        result = await db.execute(select(WorkspaceJob).where(WorkspaceJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = status
        job.completed_at = _now_kst()
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def finalize_workspace_job_with_fresh_session(
        *,
        job_id: str,
        status: str,
    ) -> None:
        async with AsyncSessionLocal() as db:
            await RepositoryWorkspaceService.finalize_workspace_job(
                db,
                job_id=job_id,
                status=status,
            )
