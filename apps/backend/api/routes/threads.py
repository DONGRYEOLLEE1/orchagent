from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.thread_patch import ThreadPatchRequest
from services.security_service import get_current_user, require_csrf
from schemas.thread import (
    ThreadDetailResponse,
    ThreadListResponse,
    ThreadMessageResponse,
    ThreadSummaryResponse,
)
from services.thread_profile_service import ThreadProfileService
from services.thread_service import ThreadService

router = APIRouter()


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    limit: int = Query(ThreadService.DEFAULT_LIMIT, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    threads = await ThreadService.list_thread_summaries(
        db, user_id=current_user.id, limit=limit
    )
    return ThreadListResponse(
        threads=[
            ThreadSummaryResponse.model_validate(thread, from_attributes=True)
            for thread in threads
        ]
    )


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    detail = await ThreadService.get_thread_detail(db, thread_id, user_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ThreadDetailResponse(
        thread=ThreadSummaryResponse.model_validate(detail.thread, from_attributes=True),
        messages=[
            ThreadMessageResponse.model_validate(message, from_attributes=True)
            for message in detail.messages
        ],
    )


@router.patch("/threads/{thread_id}", response_model=ThreadSummaryResponse)
async def patch_thread(
    thread_id: str,
    payload: ThreadPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    user_id = current_user.id
    session = await ThreadService.get_chat_session(db, thread_id, user_id=user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    await ThreadProfileService.upsert_thread_profile(
        db,
        thread_id=thread_id,
        user_id=user_id,
        title=payload.title,
        pinned=payload.pinned,
        archived=payload.archived,
    )
    summary = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadSummaryResponse.model_validate(summary, from_attributes=True)
