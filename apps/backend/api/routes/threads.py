from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.thread_patch import ThreadPatchRequest
from schemas.thread_title import ThreadAiTitleRequest
from services.security_service import get_current_user, require_csrf
from schemas.thread import (
    ThreadDetailResponse,
    ThreadListResponse,
    ThreadMessageResponse,
    ThreadSummaryResponse,
)
from services.logging_service import LoggingService
from services.thread_profile_service import ThreadProfileService
from services.thread_service import ThreadService
from services.thread_title_service import ThreadTitleService

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


@router.post("/threads/{thread_id}/ai-title", response_model=ThreadSummaryResponse)
async def generate_ai_thread_title(
    thread_id: str,
    payload: ThreadAiTitleRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    user_id = current_user.id
    session = await ThreadService.get_chat_session(db, thread_id)
    if session is not None and session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    if session is None:
        await LoggingService.get_or_create_session(db, thread_id, user_id)
        await db.commit()

    profile = await ThreadProfileService.get_thread_profile(db, thread_id, user_id)
    if profile is not None and profile.title_override:
        summary = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        return ThreadSummaryResponse.model_validate(summary, from_attributes=True)

    message_counts = await ThreadService.get_thread_message_role_counts(db, thread_id)
    if message_counts["user"] > 1:
        summary = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        return ThreadSummaryResponse.model_validate(summary, from_attributes=True)

    title = await ThreadTitleService.generate_title(payload.message)
    await ThreadProfileService.set_generated_title_if_missing(
        db,
        thread_id=thread_id,
        user_id=user_id,
        title=title,
    )

    summary = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadSummaryResponse.model_validate(summary, from_attributes=True)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    deleted = await ThreadService.delete_thread(db, thread_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
