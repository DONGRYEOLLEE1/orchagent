from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.auth import AuthUser

logger = logging.getLogger(__name__)

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"


def _password_bytes(password: str) -> bytes:
    pepper = settings.AUTH_PASSWORD_PEPPER.encode("utf-8")
    return pepper + password.encode("utf-8")


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

    admin_user = AuthUser(
        login_id=login_id,
        password_hash=hash_password(password),
        role="admin",
        status="active",
        must_change_password=True,
        display_name="Administrator",
    )
    db.add(admin_user)
    await db.commit()
    await db.refresh(admin_user)
    return admin_user
