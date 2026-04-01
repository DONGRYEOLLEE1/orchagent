from __future__ import annotations

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
from models.repository import ThreadRepositoryBinding, WorkspaceJob
from models.logging import KST


BACKEND_APP_ROOT = Path(__file__).resolve().parents[1]


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
        return RepositoryWorkspaceService._materialize_source(binding)

    @staticmethod
    async def create_workspace_for_turn(
        db: AsyncSession,
        *,
        binding: ThreadRepositoryBinding,
        turn_id,
    ) -> WorkspaceBundle:
        materialized = RepositoryWorkspaceService._materialize_source(binding)
        job_root = (
            RepositoryWorkspaceService.workspace_root()
            / f"user_{binding.user_id}"
            / f"thread_{binding.thread_id}"
            / f"turn_{turn_id}"
        )
        if job_root.exists():
            shutil.rmtree(job_root)

        repo_dir = job_root / "repo"
        artifact_dir = job_root / "artifacts"
        log_dir = job_root / "logs"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(materialized.repo_root, repo_dir)

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
    def summarize_workspace(repo_dir: Path) -> dict[str, object]:
        if not (repo_dir / ".git").exists():
            return {"changed_files": [], "diff_available": False}

        status_result = _run_checked(["git", "status", "--short"], cwd=repo_dir)
        diff_result = _run_checked(["git", "diff", "--name-only"], cwd=repo_dir)
        changed_files = [
            line.strip()
            for line in (diff_result.stdout or "").splitlines()
            if line.strip()
        ]
        return {
            "changed_files": changed_files,
            "git_status": (status_result.stdout or "").strip(),
            "diff_available": True,
        }

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
