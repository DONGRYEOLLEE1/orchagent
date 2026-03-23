from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.auth import AuthSession
from schemas.auth import (
    AuthStatusResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    SignupRequest,
)
from services.auth_service import (
    DisabledUserError,
    DuplicateEmailError,
    DuplicateLoginIdError,
    InvalidCredentialsError,
    authenticate_user,
    change_password,
    create_user,
    issue_session,
    revoke_session,
    revoke_user_sessions,
    verify_password,
)
from services.file_logger import JsonLogger
from services.security_service import (
    apply_auth_cookies,
    clear_auth_cookies,
    get_current_session,
    get_current_user,
    request_client_ip,
    request_user_agent,
    require_csrf,
    validate_request_origin,
)

router = APIRouter()


def _to_auth_user_response(user) -> AuthUserResponse:
    return AuthUserResponse.model_validate(user, from_attributes=True)


def _raise_auth_exception(error: Exception) -> None:
    if isinstance(error, (DuplicateLoginIdError, DuplicateEmailError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, InvalidCredentialsError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if isinstance(error, DisabledUserError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not active",
        )
    raise error


@router.post("/auth/signup", response_model=AuthUserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    validate_request_origin(request)
    try:
        user = await create_user(
            db,
            login_id=payload.login_id,
            password=payload.password,
            display_name=payload.display_name,
            email=payload.email,
        )
    except Exception as error:
        _raise_auth_exception(error)

    issued_session = await issue_session(
        db,
        user=user,
        user_agent=request_user_agent(request),
        ip_address=request_client_ip(request),
    )
    apply_auth_cookies(response, issued_session)
    JsonLogger.log_user(user.id, "signup", {"login_id": user.login_id})
    return _to_auth_user_response(user)


@router.post("/auth/login", response_model=AuthUserResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    validate_request_origin(request)
    try:
        user = await authenticate_user(
            db,
            login_id=payload.login_id,
            password=payload.password,
        )
    except Exception as error:
        _raise_auth_exception(error)

    issued_session = await issue_session(
        db,
        user=user,
        user_agent=request_user_agent(request),
        ip_address=request_client_ip(request),
    )
    apply_auth_cookies(response, issued_session)
    JsonLogger.log_user(user.id, "login", {"login_id": user.login_id})
    return _to_auth_user_response(user)


@router.post("/auth/logout", response_model=AuthStatusResponse)
async def logout(
    response: Response,
    session: AuthSession = Depends(get_current_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    await revoke_session(db, session)
    clear_auth_cookies(response)
    JsonLogger.log_user(session.user_id, "logout", {"session_id": session.id})
    return AuthStatusResponse(message="Logged out")


@router.get("/auth/me", response_model=AuthUserResponse)
async def me(user=Depends(get_current_user)):
    return _to_auth_user_response(user)


@router.post("/auth/change-password", response_model=AuthUserResponse)
async def update_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: AuthSession = Depends(get_current_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    user = session.user
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    await change_password(db, user=user, new_password=payload.new_password)
    await revoke_user_sessions(db, user.id)
    issued_session = await issue_session(
        db,
        user=user,
        user_agent=request_user_agent(request),
        ip_address=request_client_ip(request),
    )
    apply_auth_cookies(response, issued_session)
    JsonLogger.log_user(user.id, "change_password", {"login_id": user.login_id})
    return _to_auth_user_response(user)
