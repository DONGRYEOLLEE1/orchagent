from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from models.auth import AuthSession, AuthUser
from services.auth_service import (
    IssuedSession,
    get_auth_session_by_token,
    touch_session,
    verify_csrf_token,
)

AUTH_SESSION_COOKIE_ALIAS = settings.AUTH_SESSION_COOKIE_NAME
AUTH_CSRF_COOKIE_ALIAS = settings.AUTH_CSRF_COOKIE_NAME
AUTH_CSRF_HEADER_ALIAS = settings.AUTH_CSRF_HEADER_NAME
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_from_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _ensure_allowed_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in settings.auth_allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )

    referer_origin = _origin_from_url(request.headers.get("referer"))
    if referer_origin and referer_origin not in settings.auth_allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Referer not allowed",
        )


def request_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def apply_auth_cookies(response: Response, issued_session: IssuedSession) -> None:
    response.set_cookie(
        key=settings.AUTH_SESSION_COOKIE_NAME,
        value=issued_session.session_token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        key=settings.AUTH_CSRF_COOKIE_NAME,
        value=issued_session.csrf_token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=False,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=settings.AUTH_SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.AUTH_CSRF_COOKIE_NAME, path="/")


async def get_optional_current_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_cookie: str | None = Cookie(None, alias=AUTH_SESSION_COOKIE_ALIAS),
) -> AuthSession | None:
    session = await get_auth_session_by_token(db, session_cookie)
    if session is None:
        return None
    _ensure_allowed_origin(request)
    return await touch_session(db, session)


async def get_current_session(
    session: AuthSession | None = Depends(get_optional_current_session),
) -> AuthSession:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return session


async def get_current_user(
    session: AuthSession = Depends(get_current_session),
) -> AuthUser:
    return session.user


async def require_csrf(
    request: Request,
    session: AuthSession = Depends(get_current_session),
    csrf_cookie: str | None = Cookie(None, alias=AUTH_CSRF_COOKIE_ALIAS),
    csrf_header: str | None = Header(None, alias=AUTH_CSRF_HEADER_ALIAS),
) -> None:
    if request.method.upper() not in UNSAFE_METHODS:
        return

    _ensure_allowed_origin(request)
    if not csrf_cookie or not csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )

    if csrf_cookie != csrf_header or not verify_csrf_token(csrf_header, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )
