from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from schemas.upload import UploadBatchResponse, UploadedFileResponse
from services.security_service import get_current_user, require_csrf
from services.upload_service import UploadService

router = APIRouter()


@router.post("/uploads", response_model=UploadBatchResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    thread_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    if len(files) > settings.ATTACHMENT_MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail="Too many files in a single request")

    uploads = [
        await UploadService.create_upload(
            db,
            user_id=current_user.id,
            file=file,
            thread_id=thread_id,
        )
        for file in files
    ]
    return UploadBatchResponse(
        uploads=[
            UploadedFileResponse.model_validate(upload, from_attributes=True)
            for upload in uploads
        ]
    )
