from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.repository import ThreadRepositoryBinding
from models.upload import UploadedFile
from schemas.repository import RepositoryBindingResponse
from services.logging_service import LoggingService
from services.storage_service import StorageService


def _repo_name_from_source(source_ref: str) -> str:
    parsed = urlparse(source_ref)
    if parsed.scheme in {"http", "https", "file"}:
        candidate = Path(parsed.path).name
    else:
        candidate = Path(source_ref).name
    if candidate.endswith(".git"):
        candidate = candidate[: -len(".git")]
    return candidate or "repository"


def _source_label(binding: ThreadRepositoryBinding) -> str:
    if binding.source_type == "repo_zip":
        return binding.display_name
    return binding.source_ref


@dataclass(slots=True)
class ZipBindingResult:
    binding: ThreadRepositoryBinding
    uploaded_file: UploadedFile


class RepositoryBindingService:
    URL_SOURCE_TYPES = {"github_url", "git_url", "registered_repo"}

    @staticmethod
    def _validate_source_type(source_type: str) -> str:
        normalized = (source_type or "").strip().lower()
        if normalized not in {
            "github_url",
            "git_url",
            "repo_zip",
            "registered_repo",
        }:
            raise HTTPException(status_code=400, detail="Unsupported repository source type")
        return normalized

    @staticmethod
    def _validate_repo_url(source_ref: str, *, source_type: str) -> str:
        normalized = source_ref.strip()
        parsed = urlparse(normalized)
        if source_type == "registered_repo":
            if not normalized:
                raise HTTPException(status_code=400, detail="Registered repo path is required")
            return normalized

        if parsed.scheme not in {"http", "https", "file"}:
            raise HTTPException(status_code=400, detail="Repository URL must use http, https, or file")

        if source_type == "github_url" and "github.com" not in parsed.netloc:
            raise HTTPException(status_code=400, detail="GitHub URL is required")

        return normalized

    @staticmethod
    async def _ensure_thread(db: AsyncSession, *, thread_id: str, user_id: str) -> None:
        await LoggingService.get_or_create_session(db, thread_id, user_id)
        await db.commit()

    @staticmethod
    async def get_active_binding(
        db: AsyncSession,
        *,
        thread_id: str,
        user_id: str,
    ) -> ThreadRepositoryBinding | None:
        result = await db.execute(
            select(ThreadRepositoryBinding).where(
                ThreadRepositoryBinding.thread_id == thread_id,
                ThreadRepositoryBinding.user_id == user_id,
                ThreadRepositoryBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def to_response(binding: ThreadRepositoryBinding) -> RepositoryBindingResponse:
        return RepositoryBindingResponse(
            id=str(binding.id),
            thread_id=binding.thread_id,
            source_type=binding.source_type,
            source_label=_source_label(binding),
            display_name=binding.display_name,
            default_branch=binding.default_branch,
            pinned_commit_sha=binding.pinned_commit_sha,
            status=binding.status,
            created_at=binding.created_at,
            updated_at=binding.updated_at,
        )

    @staticmethod
    async def bind_repository(
        db: AsyncSession,
        *,
        user_id: str,
        thread_id: str,
        source_type: str,
        source_ref: str,
    ) -> ThreadRepositoryBinding:
        normalized_type = RepositoryBindingService._validate_source_type(source_type)
        if normalized_type not in RepositoryBindingService.URL_SOURCE_TYPES:
            raise HTTPException(status_code=400, detail="Use the zip binding endpoint for repository archives")
        normalized_ref = RepositoryBindingService._validate_repo_url(
            source_ref, source_type=normalized_type
        )

        await RepositoryBindingService._ensure_thread(
            db, thread_id=thread_id, user_id=user_id
        )
        existing = await RepositoryBindingService.get_active_binding(
            db, thread_id=thread_id, user_id=user_id
        )
        if existing is None:
            binding = ThreadRepositoryBinding(
                thread_id=thread_id,
                user_id=user_id,
                source_type=normalized_type,
                source_ref=normalized_ref,
                display_name=_repo_name_from_source(normalized_ref),
                status="active",
            )
            db.add(binding)
            await db.commit()
            await db.refresh(binding)
            return binding

        existing.source_type = normalized_type
        existing.source_ref = normalized_ref
        existing.display_name = _repo_name_from_source(normalized_ref)
        existing.default_branch = None
        existing.pinned_commit_sha = None
        existing.uploaded_file_id = None
        existing.status = "active"
        await db.commit()
        await db.refresh(existing)
        return existing

    @staticmethod
    async def bind_repository_zip(
        db: AsyncSession,
        *,
        user_id: str,
        thread_id: str,
        file: UploadFile,
    ) -> ZipBindingResult:
        filename = file.filename or "repository.zip"
        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Repository archive must be a .zip file")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty repository archive is not allowed")
        if len(content) > settings.REPOSITORY_BINDING_MAX_ZIP_BYTES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Repository zip exceeds {settings.REPOSITORY_BINDING_MAX_ZIP_BYTES // (1024 * 1024)}MB limit"
                ),
            )

        await RepositoryBindingService._ensure_thread(
            db, thread_id=thread_id, user_id=user_id
        )

        stored_path = StorageService.save_bytes(
            content,
            extension=".zip",
            subdir="repo_zips",
        )
        upload = UploadedFile(
            id=uuid.uuid4(),
            user_id=user_id,
            thread_id=thread_id,
            kind="repo_zip",
            source_type="repository_binding",
            processing_status="ready",
            preview_status="pending",
            file_name=filename,
            declared_extension=".zip",
            mime_type="application/zip",
            sniffed_mime_type="application/zip",
            size_bytes=len(content),
            storage_path=stored_path,
        )
        db.add(upload)
        await db.flush()

        existing = await RepositoryBindingService.get_active_binding(
            db, thread_id=thread_id, user_id=user_id
        )
        if existing is None:
            binding = ThreadRepositoryBinding(
                thread_id=thread_id,
                user_id=user_id,
                source_type="repo_zip",
                source_ref=stored_path,
                display_name=filename,
                uploaded_file_id=upload.id,
                status="active",
            )
            db.add(binding)
            await db.commit()
            await db.refresh(upload)
            await db.refresh(binding)
            return ZipBindingResult(binding=binding, uploaded_file=upload)

        existing.source_type = "repo_zip"
        existing.source_ref = stored_path
        existing.display_name = filename
        existing.default_branch = None
        existing.pinned_commit_sha = None
        existing.uploaded_file_id = upload.id
        existing.status = "active"
        await db.commit()
        await db.refresh(upload)
        await db.refresh(existing)
        return ZipBindingResult(binding=existing, uploaded_file=upload)

    @staticmethod
    async def delete_binding(
        db: AsyncSession,
        *,
        binding_id: str,
        user_id: str,
    ) -> bool:
        result = await db.execute(
            select(ThreadRepositoryBinding).where(
                ThreadRepositoryBinding.id == binding_id,
                ThreadRepositoryBinding.user_id == user_id,
            )
        )
        binding = result.scalar_one_or_none()
        if binding is None:
            return False

        await db.execute(
            delete(ThreadRepositoryBinding).where(
                ThreadRepositoryBinding.id == binding.id,
                ThreadRepositoryBinding.user_id == user_id,
            )
        )
        await db.commit()
        return True
