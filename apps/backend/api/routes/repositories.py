from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.repository import (
    RepositoryBindingEnvelope,
    RepositoryBindingRequest,
    RepositoryMaterializeRequest,
    RepositoryMaterializeResponse,
)
from services.repository_binding_service import RepositoryBindingService
from services.repository_workspace_service import RepositoryWorkspaceService
from services.security_service import get_current_user, require_csrf

router = APIRouter()


@router.get(
    "/repositories/bindings/{thread_id}",
    response_model=RepositoryBindingEnvelope,
)
async def get_repository_binding(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    binding = await RepositoryBindingService.get_active_binding(
        db,
        thread_id=thread_id,
        user_id=str(current_user.id),
    )
    return RepositoryBindingEnvelope(
        binding=(
            RepositoryBindingService.to_response(binding)
            if binding is not None
            else None
        )
    )


@router.post("/repositories/bind", response_model=RepositoryBindingEnvelope)
async def bind_repository(
    payload: RepositoryBindingRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    binding = await RepositoryBindingService.bind_repository(
        db,
        user_id=str(current_user.id),
        thread_id=payload.thread_id,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
    )
    return RepositoryBindingEnvelope(
        binding=RepositoryBindingService.to_response(binding)
    )


@router.post("/repositories/bind-zip", response_model=RepositoryBindingEnvelope)
async def bind_repository_zip(
    thread_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    result = await RepositoryBindingService.bind_repository_zip(
        db,
        user_id=str(current_user.id),
        thread_id=thread_id,
        file=file,
    )
    return RepositoryBindingEnvelope(
        binding=RepositoryBindingService.to_response(result.binding)
    )


@router.delete("/repositories/bindings/{binding_id}")
async def delete_repository_binding(
    binding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    deleted = await RepositoryBindingService.delete_binding(
        db,
        binding_id=binding_id,
        user_id=str(current_user.id),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Repository binding not found")
    return {"message": "Repository binding deleted"}


@router.post("/repositories/materialize", response_model=RepositoryMaterializeResponse)
async def materialize_repository_binding(
    payload: RepositoryMaterializeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    binding = await RepositoryBindingService.get_active_binding(
        db,
        thread_id=payload.thread_id,
        user_id=str(current_user.id),
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Repository binding not found")

    materialized = await RepositoryWorkspaceService.materialize_binding(
        db,
        binding=binding,
    )
    return RepositoryMaterializeResponse(
        binding=RepositoryBindingService.to_response(binding),
        repo_commit_sha=materialized.repo_commit_sha,
        status="ready",
    )
