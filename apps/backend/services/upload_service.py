from __future__ import annotations

import mimetypes
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

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type",
        )

    @staticmethod
    def guess_mime_type(file_name: str, fallback: str | None = None) -> str:
        guessed, _ = mimetypes.guess_type(file_name)
        return fallback or guessed or "application/octet-stream"

    @staticmethod
    async def create_upload(
        db: AsyncSession,
        *,
        user_id: str,
        file: UploadFile,
        thread_id: str | None = None,
    ) -> UploadedFile:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file upload is not allowed")
        if len(content) > settings.ATTACHMENT_MAX_BYTES:
            raise HTTPException(status_code=400, detail="File exceeds upload size limit")

        file_name = file.filename or "attachment"
        mime_type = UploadService.guess_mime_type(file_name, file.content_type)
        kind = UploadService.infer_attachment_kind(file_name=file_name, mime_type=mime_type)
        storage_path = StorageService.save_bytes(
            content,
            extension=Path(file_name).suffix,
            subdir=kind,
        )

        upload = UploadedFile(
            user_id=user_id,
            thread_id=thread_id,
            kind=kind,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=len(content),
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
    def build_attachment_snapshot(upload: UploadedFile) -> dict[str, str | int]:
        return {
            "id": str(upload.id),
            "kind": upload.kind,
            "storage_path": upload.storage_path,
            "file_name": upload.file_name,
            "mime_type": upload.mime_type,
            "size_bytes": upload.size_bytes,
        }
