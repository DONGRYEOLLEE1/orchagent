import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
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
    ThreadTelemetryResponse,
)
from services.logging_service import LoggingService
from services.thread_profile_service import ThreadProfileService
from services.thread_suggested_query_service import ThreadSuggestedQueryService
from services.thread_service import ThreadService
from services.thread_telemetry_service import ThreadTelemetryService
from services.thread_title_service import ThreadTitleService
from services.trace_service import TraceService

router = APIRouter()
logger = logging.getLogger(__name__)


def _absolutize_attachment_urls(
    request: Request,
    messages: list[ThreadMessageResponse],
) -> list[ThreadMessageResponse]:
    base_url = str(request.base_url).rstrip("/")
    normalized: list[ThreadMessageResponse] = []
    for message in messages:
        attachments = [
            attachment.model_copy(
                update={
                    "url": attachment.url
                    if attachment.url.startswith("http://")
                    or attachment.url.startswith("https://")
                    else f"{base_url}{attachment.url}",
                }
            )
            for attachment in message.attachments
        ]
        normalized.append(message.model_copy(update={"attachments": attachments}))
    return normalized


async def _safe_create_trace_event(**kwargs) -> None:
    db = kwargs.pop("db")
    try:
        await TraceService.create_event(db, **kwargs)
    except Exception as exc:
        logger.warning("Trace event persistence skipped: %s", exc)


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
    request: Request,
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    detail = await ThreadService.get_thread_detail(db, thread_id, user_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = [
        ThreadMessageResponse.model_validate(message, from_attributes=True)
        for message in detail.messages
    ]
    return ThreadDetailResponse(
        thread=ThreadSummaryResponse.model_validate(detail.thread, from_attributes=True),
        messages=_absolutize_attachment_urls(request, messages),
    )


@router.get("/threads/{thread_id}/messages/{message_id}/attachments/{attachment_index}")
async def get_thread_message_attachment(
    thread_id: str,
    message_id: UUID,
    attachment_index: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    storage_path = await ThreadService.get_thread_message_attachment_path(
        db,
        thread_id=thread_id,
        message_id=message_id,
        attachment_index=attachment_index,
        user_id=current_user.id,
    )
    if storage_path is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = Path(storage_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found")

    return FileResponse(file_path)


@router.get("/threads/{thread_id}/telemetry", response_model=ThreadTelemetryResponse)
async def get_thread_telemetry(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = await ThreadService.get_chat_session(
        db, thread_id, user_id=current_user.id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    telemetry = await ThreadTelemetryService.get_thread_telemetry(db, thread_id)
    return ThreadTelemetryResponse(
        thread_id=thread_id,
        reasoning_summary=telemetry.reasoning_summary,
        suggested_queries=telemetry.suggested_queries,
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

    if payload.title is not None:
        await _safe_create_trace_event(
            db=db,
            thread_id=thread_id,
            event_type="thread_title_manual",
            node_name="thread_profile",
            payload={
                "event_type": "thread_title_manual",
                "thread_id": thread_id,
                "title": summary.title,
            },
        )
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
    policy_stats = await ThreadService.get_thread_title_policy_stats(db, thread_id)
    has_legacy_or_manual_override = bool(
        profile is not None
        and profile.title_override
        and policy_stats.ai_title_generation_count == 0
    )

    should_run_initial = (
        policy_stats.ai_title_generation_count == 0
        and policy_stats.user_turn_count == 1
        and not policy_stats.has_manual_title_event
        and not has_legacy_or_manual_override
        and payload.message is not None
    )
    should_run_fifth_turn_refresh = (
        policy_stats.ai_title_generation_count == 1
        and policy_stats.assistant_turn_count >= 5
        and not policy_stats.has_manual_title_event
    )

    if not should_run_initial and not should_run_fifth_turn_refresh:
        summary = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        return ThreadSummaryResponse.model_validate(summary, from_attributes=True)

    if should_run_initial:
        title = await ThreadTitleService.generate_title(payload.message or "")
    else:
        thread_messages = await ThreadService.get_thread_messages(db, thread_id)
        transcript_messages = [
            (message.role, message.content)
            for message in thread_messages
            if message.role in {"user", "assistant"}
            and not (
                message.role == "user"
                and message.content.startswith("[User Action]:")
            )
        ]
        fallback_message = profile.title_override if profile and profile.title_override else (
            payload.message or " ".join(
                content for role, content in transcript_messages if role == "user"
            )
        )
        title = await ThreadTitleService.generate_title_from_transcript(
            transcript_messages,
            fallback_message=fallback_message,
        )

    await ThreadProfileService.upsert_thread_profile(
        db,
        thread_id=thread_id,
        user_id=user_id,
        title=title,
    )
    await _safe_create_trace_event(
        db=db,
        thread_id=thread_id,
        event_type="thread_title_ai_generated",
        node_name="thread_profile",
        payload={
            "event_type": "thread_title_ai_generated",
            "thread_id": thread_id,
            "title": title,
            "generation_index": policy_stats.ai_title_generation_count + 1,
            "trigger": "initial_user_turn" if should_run_initial else "five_turn_refresh",
        },
    )

    summary = await ThreadService.get_thread_summary(db, thread_id, user_id=user_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadSummaryResponse.model_validate(summary, from_attributes=True)


@router.post(
    "/threads/{thread_id}/suggested-queries", response_model=ThreadTelemetryResponse
)
async def generate_suggested_queries(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    session = await ThreadService.get_chat_session(
        db, thread_id, user_id=current_user.id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    context = await ThreadService.get_latest_suggestion_context(db, thread_id)
    if context is not None:
        suggestions = await ThreadSuggestedQueryService.generate_suggestions(
            user_message=context.user_content,
            assistant_message=context.assistant_content,
        )
        if suggestions:
            await _safe_create_trace_event(
                db=db,
                thread_id=thread_id,
                event_type="suggested_queries_summary",
                node_name="assistant",
                payload={
                    "event_type": "suggested_queries_summary",
                    "node": "assistant",
                    "suggested_queries": suggestions,
                },
            )

    telemetry = await ThreadTelemetryService.get_thread_telemetry(db, thread_id)
    return ThreadTelemetryResponse(
        thread_id=thread_id,
        reasoning_summary=telemetry.reasoning_summary,
        suggested_queries=telemetry.suggested_queries,
    )


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
