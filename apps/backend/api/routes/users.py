from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.auth import AuthUserResponse
from schemas.user_patch import AdminUserPatchRequest, UserSelfPatchRequest
from services.admin_user_service import AdminUserService
from services.auth_service import DuplicateEmailError
from services.security_service import (
    get_current_admin_user,
    get_current_user,
    require_csrf,
)
from services.user_profile_service import UserProfileService

router = APIRouter()


def _to_auth_user_response(user) -> AuthUserResponse:
    return AuthUserResponse.model_validate(user, from_attributes=True)


@router.patch("/users/me", response_model=AuthUserResponse)
async def patch_self(
    payload: UserSelfPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    try:
        user = await UserProfileService.patch_self(
            db,
            user_id=current_user.id,
            display_name=payload.display_name,
            email=payload.email,
        )
    except DuplicateEmailError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))

    return _to_auth_user_response(user)


@router.patch("/users/{user_id}", response_model=AuthUserResponse)
async def patch_user(
    user_id: str,
    payload: AdminUserPatchRequest,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
    _: None = Depends(require_csrf),
):
    try:
        user = await AdminUserService.patch_user_status(
            db,
            actor_user_id=admin_user.id,
            target_user_id=user_id,
            status=payload.status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))

    return _to_auth_user_response(user)
