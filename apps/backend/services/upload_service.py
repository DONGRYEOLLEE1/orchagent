from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.upload import UploadedFile
from services.storage_service import StorageService


SUPPORTED_ATTACHMENT_KINDS: dict[str, tuple[str, ...]] = {
    "image": (".png", ".jpg", ".jpeg", ".webp"),
    "pdf": (".pdf",),
    "spreadsheet": (".xlsx",),
    "csv": (".csv",),
    "json": (".json",),
    "docx": (".docx",),
}

def _format_size_limit(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.0f}MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f}KB"
    return f"{size_bytes}B"


class UploadValidationError(Exception):
    def __init__(self, error_code: str, detail: str):
        super().__init__(detail)
        self.error_code = error_code
        self.detail = detail


@dataclass(slots=True)
class PreparedUpload:
    input_index: int
    file_name: str
    declared_extension: str | None
    kind: str
    mime_type: str
    sniffed_mime_type: str
    size_bytes: int
    content: bytes
    source_type: str
    processing_status: str
    preview_status: str


@dataclass(slots=True)
class UploadBatchError:
    input_index: int
    file_name: str
    error_code: str
    detail: str


class UploadService:
    @staticmethod
    def infer_attachment_kind(*, file_name: str, mime_type: str | None) -> str:
        extension = Path(file_name).suffix.lower()
        resolved_mime = (mime_type or "").lower()

        if resolved_mime.startswith("image/") or extension in SUPPORTED_ATTACHMENT_KINDS["image"]:
            return "image"
        if extension in SUPPORTED_ATTACHMENT_KINDS["pdf"] or resolved_mime == "application/pdf":
            return "pdf"
        if (
            extension in SUPPORTED_ATTACHMENT_KINDS["spreadsheet"]
            or resolved_mime
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ):
            return "spreadsheet"
        if extension in SUPPORTED_ATTACHMENT_KINDS["csv"] or resolved_mime in {
            "text/csv",
            "application/csv",
            "text/plain",
        }:
            return "csv"
        if extension in SUPPORTED_ATTACHMENT_KINDS["json"] or resolved_mime in {
            "application/json",
            "text/json",
        }:
            return "json"
        if (
            extension in SUPPORTED_ATTACHMENT_KINDS["docx"]
            or resolved_mime
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            return "docx"

        raise UploadValidationError(
            error_code="unsupported_file_type",
            detail="Unsupported file type",
        )

    @staticmethod
    def guess_mime_type(file_name: str, fallback: str | None = None) -> str:
        guessed, _ = mimetypes.guess_type(file_name)
        return fallback or guessed or "application/octet-stream"

    @staticmethod
    def sniff_mime_type(file_name: str, content: bytes, fallback: str) -> str:
        extension = Path(file_name).suffix.lower()
        if content.startswith(b"%PDF-"):
            return "application/pdf"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return "image/webp"
        if extension == ".json":
            return "application/json"
        if extension == ".csv":
            return "text/csv"
        if extension == ".docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if extension == ".xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return fallback

    @staticmethod
    def max_bytes_for_kind(kind: str) -> int:
        limits = {
            "image": settings.ATTACHMENT_MAX_IMAGE_BYTES,
            "pdf": settings.ATTACHMENT_MAX_PDF_BYTES,
            "spreadsheet": settings.ATTACHMENT_MAX_SPREADSHEET_BYTES,
            "csv": settings.ATTACHMENT_MAX_CSV_BYTES,
            "json": settings.ATTACHMENT_MAX_JSON_BYTES,
            "docx": settings.ATTACHMENT_MAX_DOCX_BYTES,
        }
        return limits[kind]

    @staticmethod
    def preview_status_for_kind(kind: str) -> str:
        if kind == "image":
            return "ready"
        return "pending"

    @staticmethod
    async def prepare_upload(
        *,
        file: UploadFile,
        input_index: int,
        source_type: str = "device",
    ) -> PreparedUpload:
        content = await file.read()
        if not content:
            raise UploadValidationError(
                error_code="empty_file",
                detail="Empty file upload is not allowed",
            )

        file_name = file.filename or "attachment"
        declared_extension = Path(file_name).suffix.lower() or None
        mime_type = UploadService.guess_mime_type(file_name, file.content_type)
        sniffed_mime_type = UploadService.sniff_mime_type(file_name, content, mime_type)
        kind = UploadService.infer_attachment_kind(
            file_name=file_name,
            mime_type=sniffed_mime_type,
        )
        size_bytes = len(content)
        max_bytes = UploadService.max_bytes_for_kind(kind)
        if size_bytes > max_bytes:
            raise UploadValidationError(
                error_code="file_too_large",
                detail=f"{kind.upper()} file exceeds {_format_size_limit(max_bytes)} limit",
            )

        return PreparedUpload(
            input_index=input_index,
            file_name=file_name,
            declared_extension=declared_extension,
            kind=kind,
            mime_type=mime_type,
            sniffed_mime_type=sniffed_mime_type,
            size_bytes=size_bytes,
            content=content,
            source_type=source_type,
            processing_status="ready",
            preview_status=UploadService.preview_status_for_kind(kind),
        )

    @staticmethod
    async def prepare_upload_batch(
        *,
        files: list[UploadFile],
        source_type: str = "device",
    ) -> tuple[list[PreparedUpload], list[UploadBatchError], int]:
        if len(files) > settings.ATTACHMENT_MAX_FILES_PER_REQUEST:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files in a single request (max {settings.ATTACHMENT_MAX_FILES_PER_REQUEST})",
            )

        prepared_uploads: list[PreparedUpload] = []
        errors: list[UploadBatchError] = []

        for index, file in enumerate(files):
            try:
                prepared_uploads.append(
                    await UploadService.prepare_upload(
                        file=file,
                        input_index=index,
                        source_type=source_type,
                    )
                )
            except UploadValidationError as exc:
                errors.append(
                    UploadBatchError(
                        input_index=index,
                        file_name=file.filename or f"file-{index + 1}",
                        error_code=exc.error_code,
                        detail=exc.detail,
                    )
                )

        total_size_bytes = sum(upload.size_bytes for upload in prepared_uploads)
        if total_size_bytes > settings.ATTACHMENT_MAX_TOTAL_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Total upload size exceeds {_format_size_limit(settings.ATTACHMENT_MAX_TOTAL_BYTES)} limit",
            )

        return prepared_uploads, errors, total_size_bytes

    @staticmethod
    async def create_upload_from_prepared(
        db: AsyncSession,
        *,
        user_id: str,
        prepared: PreparedUpload,
        thread_id: str | None = None,
        storage_path: str | None = None,
    ) -> UploadedFile:
        resolved_storage_path = storage_path or StorageService.save_bytes(
            prepared.content,
            extension=prepared.declared_extension,
            subdir=prepared.kind,
        )

        upload = UploadedFile(
            user_id=user_id,
            thread_id=thread_id,
            kind=prepared.kind,
            source_type=prepared.source_type,
            processing_status=prepared.processing_status,
            preview_status=prepared.preview_status,
            file_name=prepared.file_name,
            declared_extension=prepared.declared_extension,
            mime_type=prepared.mime_type,
            sniffed_mime_type=prepared.sniffed_mime_type,
            size_bytes=prepared.size_bytes,
            storage_path=resolved_storage_path,
        )
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        setattr(upload, "input_index", prepared.input_index)
        return upload

    @staticmethod
    async def create_upload(
        db: AsyncSession,
        *,
        user_id: str,
        file: UploadFile,
        thread_id: str | None = None,
    ) -> UploadedFile:
        try:
            prepared = await UploadService.prepare_upload(file=file, input_index=0)
        except UploadValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.detail) from exc

        return await UploadService.create_upload_from_prepared(
            db,
            user_id=user_id,
            prepared=prepared,
            thread_id=thread_id,
        )

    @staticmethod
    async def register_generated_artifact(
        db: AsyncSession,
        *,
        user_id: str,
        thread_id: str,
        artifact,
    ) -> UploadedFile:
        storage_path = str(artifact.storage_path)
        path = Path(storage_path)
        mime_type = artifact.mime_type or UploadService.guess_mime_type(path.name)
        sniffed_mime_type = UploadService.guess_mime_type(path.name, mime_type)
        kind = str(getattr(artifact, "kind", "artifact") or "artifact")
        upload = UploadedFile(
            user_id=user_id,
            thread_id=thread_id,
            kind=kind,
            source_type="generated_artifact",
            processing_status="ready",
            preview_status=UploadService.preview_status_for_kind(kind)
            if kind in {"image", "pdf", "spreadsheet", "csv", "json", "docx"}
            else "pending",
            file_name=str(getattr(artifact, "file_name", path.name) or path.name),
            declared_extension=path.suffix.lower() or None,
            mime_type=mime_type,
            sniffed_mime_type=sniffed_mime_type,
            size_bytes=int(getattr(artifact, "size_bytes", path.stat().st_size) or path.stat().st_size),
            storage_path=storage_path,
        )
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        return upload

    @staticmethod
    async def resolve_uploads(
        db: AsyncSession,
        *,
        upload_ids: list[str] | None,
        user_id: str,
    ) -> list[UploadedFile]:
        if not upload_ids:
            return []

        resolved_ids: list[UUID] = []
        for upload_id in upload_ids:
            try:
                resolved_ids.append(UUID(str(upload_id)))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid attachment id") from exc

        stmt = select(UploadedFile).where(
            UploadedFile.id.in_(resolved_ids),
            UploadedFile.user_id == user_id,
        )
        result = await db.execute(stmt)
        uploads = result.scalars().all()
        uploads_by_id = {str(upload.id): upload for upload in uploads}
        ordered_uploads = [uploads_by_id.get(str(upload_id)) for upload_id in resolved_ids]
        if any(upload is None for upload in ordered_uploads):
            raise HTTPException(status_code=404, detail="Attachment not found")
        return [upload for upload in ordered_uploads if upload is not None]

    @staticmethod
    def build_attachment_snapshot(
        upload: UploadedFile,
        *,
        title: str | None = None,
    ) -> dict[str, str | int | None]:
        return {
            "id": str(upload.id),
            "upload_id": str(upload.id),
            "kind": upload.kind,
            "source_type": upload.source_type,
            "processing_status": upload.processing_status,
            "preview_status": upload.preview_status,
            "storage_path": upload.storage_path,
            "file_name": upload.file_name,
            "declared_extension": upload.declared_extension,
            "mime_type": upload.mime_type,
            "sniffed_mime_type": upload.sniffed_mime_type,
            "size_bytes": upload.size_bytes,
            "title": title,
        }
