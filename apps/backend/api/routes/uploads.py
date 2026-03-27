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

    uploads = [
        await UploadService.create_upload_from_prepared(
            db,
            user_id=current_user.id,
            prepared=prepared_upload,
            thread_id=thread_id,
        )
        for prepared_upload in prepared_uploads
    ]
    await _safe_create_upload_trace(
        db=db,
        thread_id=thread_id,
        user_id=current_user.id,
        payload={
            "accepted_count": len(uploads),
            "failed_count": len(errors),
            "total_size_bytes": total_size_bytes,
            "kinds": [upload.kind for upload in uploads],
        },
    )
    return UploadBatchResponse(
        uploads=[
            UploadedFileResponse.model_validate(upload, from_attributes=True)
            for upload in uploads
        ],
        errors=[
            UploadErrorResponse(
                input_index=error.input_index,
                file_name=error.file_name,
                error_code=error.error_code,
                detail=error.detail,
            )
            for error in errors
        ],
        accepted_count=len(uploads),
        failed_count=len(errors),
        total_size_bytes=total_size_bytes,
    )
