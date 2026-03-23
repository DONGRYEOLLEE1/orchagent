from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.security_service import get_current_user
from schemas.thread import (
    ThreadDetailResponse,
    ThreadListResponse,
    ThreadMessageResponse,
    ThreadSummaryResponse,
)
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
