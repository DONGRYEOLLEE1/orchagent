from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.memory import (
    PersonalMemoryCreateRequest,
    PersonalMemoryEntryResponse,
    PersonalMemoryListResponse,
    PersonalizationInstructionCreateRequest,
    PersonalizationInstructionListResponse,
    PersonalizationInstructionPatchRequest,
    PersonalizationInstructionResponse,
    UserMemorySettingsPatchRequest,
    UserPersonalizationSettingsPatchRequest,
    UserMemorySettingsResponse,
)
from services.memory_service import MemoryService
from services.personalization_instruction_service import (
    PersonalizationInstructionService,
    PersonalizationInstructionValidationError,
)
from services.security_service import get_current_user, require_csrf

router = APIRouter()


@router.get(
    "/users/me/memory/settings",
    response_model=UserMemorySettingsResponse,
)
async def get_memory_settings(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Memory and personalization settings share one canonical row, but they keep
    # separate external API namespaces so the UI can evolve each surface independently.
    settings = await MemoryService.get_or_create_settings(db, current_user.id)
    return UserMemorySettingsResponse.model_validate(settings, from_attributes=True)


@router.patch(
    "/users/me/memory/settings",
    response_model=UserMemorySettingsResponse,
)
async def patch_memory_settings(
    payload: UserMemorySettingsPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    settings = await MemoryService.update_settings(
        db,
        user_id=current_user.id,
        memory_enabled=payload.memory_enabled,
        instructions_enabled=payload.instructions_enabled,
        allow_explicit_memory=payload.allow_explicit_memory,
        allow_inferred_memory=payload.allow_inferred_memory,
        allow_chat_history_reference=payload.allow_chat_history_reference,
        default_memory_mode=payload.default_memory_mode,
    )
    return UserMemorySettingsResponse.model_validate(settings, from_attributes=True)


@router.get(
    "/users/me/personalization/settings",
    response_model=UserMemorySettingsResponse,
)
async def get_personalization_settings(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    settings = await MemoryService.get_or_create_settings(db, current_user.id)
    return UserMemorySettingsResponse.model_validate(settings, from_attributes=True)


@router.patch(
    "/users/me/personalization/settings",
    response_model=UserMemorySettingsResponse,
)
async def patch_personalization_settings(
    payload: UserPersonalizationSettingsPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    settings = await MemoryService.update_settings(
        db,
        user_id=current_user.id,
        instructions_enabled=payload.instructions_enabled,
    )
    return UserMemorySettingsResponse.model_validate(settings, from_attributes=True)


@router.get("/users/me/memory", response_model=PersonalMemoryListResponse)
async def list_personal_memories(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    memories = await MemoryService.list_memories(db, user_id=current_user.id, limit=limit)
    return PersonalMemoryListResponse(
        memories=[
            PersonalMemoryEntryResponse.model_validate(memory, from_attributes=True)
            for memory in memories
        ]
    )


@router.post(
    "/users/me/memory",
    response_model=PersonalMemoryEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_personal_memory(
    payload: PersonalMemoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    settings = await MemoryService.get_or_create_settings(db, current_user.id)
    if not settings.allow_explicit_memory:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Explicit memory creation is disabled.",
        )
    memory = await MemoryService.create_memory(
        db,
        user_id=current_user.id,
        title=payload.title,
        content_text=payload.content_text,
        category=payload.category,
        scope_type=payload.scope_type,
        source_type="explicit",
    )
    return PersonalMemoryEntryResponse.model_validate(memory, from_attributes=True)


@router.get(
    "/users/me/personalization/instructions",
    response_model=PersonalizationInstructionListResponse,
)
async def list_personalization_instructions(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    instructions = await PersonalizationInstructionService.list_instructions(
        db,
        user_id=current_user.id,
    )
    return PersonalizationInstructionListResponse(
        instructions=[
            PersonalizationInstructionResponse.model_validate(
                instruction,
                from_attributes=True,
            )
            for instruction in instructions
        ]
    )


@router.post(
    "/users/me/personalization/instructions",
    response_model=PersonalizationInstructionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_personalization_instruction(
    payload: PersonalizationInstructionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    try:
        instruction = await PersonalizationInstructionService.create_instruction(
            db,
            user_id=current_user.id,
            instruction_type=payload.instruction_type,
            title=payload.title,
            content_text=payload.content_text,
            enabled=payload.enabled,
        )
    except PersonalizationInstructionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return PersonalizationInstructionResponse.model_validate(
        instruction,
        from_attributes=True,
    )


@router.patch(
    "/users/me/personalization/instructions/{instruction_id}",
    response_model=PersonalizationInstructionResponse,
)
async def patch_personalization_instruction(
    instruction_id: UUID,
    payload: PersonalizationInstructionPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    try:
        instruction = await PersonalizationInstructionService.update_instruction(
            db,
            user_id=current_user.id,
            instruction_id=instruction_id,
            instruction_type=payload.instruction_type,
            title=payload.title,
            content_text=payload.content_text,
            enabled=payload.enabled,
        )
    except PersonalizationInstructionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if instruction is None:
        raise HTTPException(status_code=404, detail="Instruction not found")

    return PersonalizationInstructionResponse.model_validate(
        instruction,
        from_attributes=True,
    )


@router.delete(
    "/users/me/personalization/instructions/{instruction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_personalization_instruction(
    instruction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    deleted = await PersonalizationInstructionService.delete_instruction(
        db,
        user_id=current_user.id,
        instruction_id=instruction_id,
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail="Instruction not found")


@router.delete("/users/me/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal_memory(
    memory_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    deleted = await MemoryService.delete_memory(
        db, user_id=current_user.id, memory_id=memory_id
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail="Memory not found")
