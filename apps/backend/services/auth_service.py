from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
import logging
import re
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import settings
from models.auth import KST, AuthSession, AuthUser
from services.file_logger import JsonLogger

logger = logging.getLogger(__name__)

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
LOWERCASE_PATTERN = re.compile(r"[a-z]")
DIGIT_PATTERN = re.compile(r"\d")


class AuthServiceError(Exception):
    pass


class DuplicateLoginIdError(AuthServiceError):
    pass


class DuplicateEmailError(AuthServiceError):
    pass


class InvalidCredentialsError(AuthServiceError):
    pass


class DisabledUserError(AuthServiceError):
    pass


class PasswordPolicyError(AuthServiceError):
    pass


@dataclass(slots=True)
class IssuedSession:
    session: AuthSession
    session_token: str
    csrf_token: str


def normalize_login_id(login_id: str) -> str:
    return login_id.strip().lower()


def _password_bytes(password: str) -> bytes:
    pepper = settings.AUTH_PASSWORD_PEPPER.encode("utf-8")
    return pepper + password.encode("utf-8")


def _token_hash(raw_token: str) -> str:
    payload = settings.AUTH_TOKEN_PEPPER.encode("utf-8") + raw_token.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_password_policy(password: str) -> None:
    errors: list[str] = []

    if len(password) < settings.AUTH_PASSWORD_MIN_LENGTH:
        errors.append(
            f"Password must be at least {settings.AUTH_PASSWORD_MIN_LENGTH} characters long."
        )
    if settings.AUTH_PASSWORD_REQUIRE_LOWERCASE and not LOWERCASE_PATTERN.search(
        password
    ):
        errors.append("Password must include at least one lowercase letter.")
    if settings.AUTH_PASSWORD_REQUIRE_NUMBER and not DIGIT_PATTERN.search(password):
        errors.append("Password must include at least one number.")

    if errors:
        raise PasswordPolicyError(" ".join(errors))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        _password_bytes(password),
        salt,
        settings.AUTH_PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return (
        f"{PASSWORD_HASH_ALGORITHM}"
        f"${settings.AUTH_PBKDF2_ITERATIONS}"
        f"${salt_b64}"
        f"${digest_b64}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_str, salt_b64, digest_b64 = stored_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False

    try:
        iterations = int(iterations_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        _password_bytes(password),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate, expected)


async def get_user_by_login_id(db: AsyncSession, login_id: str) -> AuthUser | None:
    normalized = normalize_login_id(login_id)
    result = await db.execute(select(AuthUser).where(AuthUser.login_id == normalized))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> AuthUser | None:
    result = await db.execute(select(AuthUser).where(AuthUser.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    login_id: str,
    password: str,
    display_name: str | None = None,
    email: str | None = None,
    role: str = "user",
    status: str = "active",
    must_change_password: bool = False,
    enforce_password_policy: bool = True,
) -> AuthUser:
    normalized_login_id = normalize_login_id(login_id)
    normalized_email = email.strip().lower() if email else None

    if not normalized_login_id:
        raise PasswordPolicyError("Login ID must not be empty.")

    if enforce_password_policy:
        validate_password_policy(password)

    existing_user = await get_user_by_login_id(db, normalized_login_id)
    if existing_user is not None:
        raise DuplicateLoginIdError("Login ID is already in use.")

    if normalized_email:
        result = await db.execute(
            select(AuthUser).where(AuthUser.email == normalized_email)
        )
        existing_email = result.scalar_one_or_none()
        if existing_email is not None:
            raise DuplicateEmailError("Email is already in use.")

    user = AuthUser(
        login_id=normalized_login_id,
        password_hash=hash_password(password),
        role=role,
        status=status,
        must_change_password=must_change_password,
        display_name=display_name.strip() if display_name else None,
        email=normalized_email,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    JsonLogger.log_user(
        user.id,
        "user_created",
        {
            "login_id": user.login_id,
            "role": user.role,
        },
    )
    return user


async def authenticate_user(
    db: AsyncSession, *, login_id: str, password: str
) -> AuthUser:
    user = await get_user_by_login_id(db, login_id)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid credentials.")

    if user.status != "active":
        raise DisabledUserError("User is not active.")

    return user


async def issue_session(
    db: AsyncSession,
    *,
    user: AuthUser,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> IssuedSession:
    now = datetime.now(KST)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)

    session = AuthSession(
        user_id=user.id,
        session_token_hash=_token_hash(session_token),
        csrf_token_hash=_token_hash(csrf_token),
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=now + timedelta(hours=settings.AUTH_SESSION_TTL_HOURS),
    )
    user.last_login_at = now
    db.add(session)
    await db.commit()
    await db.refresh(session)

    JsonLogger.log_user(
        user.id,
        "session_issued",
        {
            "session_id": session.id,
        },
    )
    return IssuedSession(session=session, session_token=session_token, csrf_token=csrf_token)


async def get_auth_session_by_token(
    db: AsyncSession, raw_session_token: str | None
) -> AuthSession | None:
    if not raw_session_token:
        return None

    now = datetime.now(KST)
    result = await db.execute(
        select(AuthSession)
        .options(selectinload(AuthSession.user))
        .where(
            AuthSession.session_token_hash == _token_hash(raw_session_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    return result.scalar_one_or_none()


def verify_csrf_token(raw_csrf_token: str | None, session: AuthSession) -> bool:
    if not raw_csrf_token:
        return False
    return hmac.compare_digest(session.csrf_token_hash, _token_hash(raw_csrf_token))


async def touch_session(db: AsyncSession, session: AuthSession) -> AuthSession:
    session.last_seen_at = datetime.now(KST)
    await db.commit()
    await db.refresh(session)
    return session


async def revoke_session(db: AsyncSession, session: AuthSession) -> None:
    session_id = session.id
    user_id = session.user_id
    if session.revoked_at is None:
        session.revoked_at = datetime.now(KST)
        await db.commit()
    JsonLogger.log_user(
        user_id,
        "session_revoked",
        {
            "session_id": session_id,
        },
    )


async def revoke_session_by_token(
    db: AsyncSession, raw_session_token: str | None
) -> None:
    session = await get_auth_session_by_token(db, raw_session_token)
    if session is None:
        return
    await revoke_session(db, session)


async def revoke_user_sessions(
    db: AsyncSession, user_id: str, *, exclude_session_id: str | None = None
) -> int:
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    sessions = result.scalars().all()
    revoked_count = 0
    now = datetime.now(KST)
    for session in sessions:
        if exclude_session_id and session.id == exclude_session_id:
            continue
        session.revoked_at = now
        revoked_count += 1

    if revoked_count > 0:
        await db.commit()
    return revoked_count


async def change_password(
    db: AsyncSession,
    *,
    user: AuthUser,
    new_password: str,
    enforce_password_policy: bool = True,
) -> AuthUser:
    if enforce_password_policy:
        validate_password_policy(new_password)

    now = datetime.now(KST)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.must_change_password = False
    await db.commit()
    await db.refresh(user)

    JsonLogger.log_user(
        user.id,
        "password_changed",
        {
            "login_id": user.login_id,
        },
    )
    return user


async def ensure_bootstrap_admin(db: AsyncSession) -> AuthUser | None:
    if not settings.AUTH_BOOTSTRAP_ADMIN_ENABLED:
        return None

    login_id = settings.AUTH_BOOTSTRAP_ADMIN_LOGIN_ID.strip()
    password = settings.AUTH_BOOTSTRAP_ADMIN_PASSWORD
    if not login_id or not password:
        logger.warning("Bootstrap admin is enabled but login id or password is empty.")
        return None

    result = await db.execute(select(AuthUser).where(AuthUser.login_id == login_id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        if existing.role != "admin":
            logger.warning(
                "Bootstrap admin login_id '%s' already exists without admin role.",
                login_id,
            )
        return existing

    if password == "admin1":
        logger.warning(
            "Bootstrap admin password is using the default credential. "
            "Change AUTH_BOOTSTRAP_ADMIN_PASSWORD outside local development."
        )

    admin_user = await create_user(
        db,
        login_id=login_id,
        password=password,
        display_name="Administrator",
        role="admin",
        status="active",
        must_change_password=True,
        enforce_password_policy=False,
    )
    JsonLogger.log_user(
        admin_user.id,
        "bootstrap_admin_seeded",
        {
            "login_id": admin_user.login_id,
        },
    )
    return admin_user
