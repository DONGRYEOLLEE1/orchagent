from __future__ import annotations

import inspect

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from schemas.upload import UploadBatchResponse, UploadErrorResponse, UploadedFileResponse
from services.security_service import get_current_user, require_csrf
from services.trace_service import TraceService
from services.upload_service import UploadService

router = APIRouter()


async def _safe_create_upload_trace(
    *,
    db: AsyncSession,
    thread_id: str | None,
    user_id: str,
    payload: dict,
) -> None:
    add_all = getattr(db, "add_all", None)
    if not thread_id or add_all is None or inspect.iscoroutinefunction(add_all):
        return

    try:
        await TraceService.create_event(
            db,
            thread_id=thread_id,
            event_type="upload_batch",
            node_name="uploads",
            payload=payload,
            user_id=user_id,
        )
    except Exception:
        return


@router.post("/uploads", response_model=UploadBatchResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    thread_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    current_user_id = str(current_user.id)

    if len(files) > settings.ATTACHMENT_MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files in a single request (max {settings.ATTACHMENT_MAX_FILES_PER_REQUEST})",
        )

    prepared_uploads, errors, total_size_bytes = await UploadService.prepare_upload_batch(
        files=files,
        source_type="device",
    )
    if not prepared_uploads and errors:
        raise HTTPException(status_code=400, detail=errors[0].detail)

    upload_responses: list[UploadedFileResponse] = []
    for prepared_upload in prepared_uploads:
        upload = await UploadService.create_upload_from_prepared(
            db,
            user_id=current_user_id,
            prepared=prepared_upload,
            thread_id=thread_id,
        )
        upload_responses.append(
            UploadedFileResponse(
                id=upload.id,
                input_index=getattr(upload, "input_index", None),
                kind=upload.kind,
                source_type=upload.source_type,
                processing_status=upload.processing_status,
                preview_status=upload.preview_status,
                file_name=upload.file_name,
                declared_extension=upload.declared_extension,
                mime_type=upload.mime_type,
                sniffed_mime_type=upload.sniffed_mime_type,
                size_bytes=upload.size_bytes,
                created_at=upload.created_at,
            )
        )
    await _safe_create_upload_trace(
        db=db,
        thread_id=thread_id,
        user_id=current_user_id,
        payload={
            "accepted_count": len(upload_responses),
            "failed_count": len(errors),
            "total_size_bytes": total_size_bytes,
            "kinds": [prepared.kind for prepared in prepared_uploads],
        },
    )
    return UploadBatchResponse(
        uploads=upload_responses,
        errors=[
            UploadErrorResponse(
                input_index=error.input_index,
                file_name=error.file_name,
                error_code=error.error_code,
                detail=error.detail,
            )
            for error in errors
        ],
        accepted_count=len(upload_responses),
        failed_count=len(errors),
        total_size_bytes=total_size_bytes,
    )
