import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import AuditLog, AuthSession, Role, User
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
password_hasher = PasswordHasher()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))
DbSession = Annotated[AsyncSession, Depends(get_db)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _is_locked(user: User, now: datetime) -> bool:
    locked_until = user.locked_until
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > now


def _audit(
    request: Request,
    *,
    action: str,
    outcome: str,
    actor_user_id: UUID | None = None,
    resource_id: str | None = None,
) -> AuditLog:
    user_agent = request.headers.get("user-agent")
    return AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type="user_session",
        resource_id=resource_id,
        outcome=outcome,
        source_ip=request.client.host if request.client else None,
        user_agent=user_agent[:1024] if user_agent else None,
    )


def _check_csrf(request: Request, auth_session: AuthSession) -> None:
    cookie_name = get_settings().csrf_cookie_name
    cookie_token = request.cookies.get(cookie_name)
    header_token = request.headers.get("x-csrf-token")
    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
        or not secrets.compare_digest(_digest(cookie_token), auth_session.csrf_token_hash)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf_validation_failed")


async def get_auth_session(
    request: Request,
    db: DbSession,
) -> AuthSession:
    cookie_name = get_settings().session_cookie_name
    raw_token = request.cookies.get(cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required"
        )

    statement = (
        select(AuthSession)
        .options(
            selectinload(AuthSession.user).selectinload(User.roles).selectinload(Role.permissions)
        )
        .where(
            AuthSession.token_hash == _digest(raw_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    auth_session = (await db.execute(statement)).scalar_one_or_none()
    if auth_session is None or not auth_session.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required"
        )
    return auth_session


def require_permission(permission_key: str):
    async def permission_guard(
        request: Request,
        db: DbSession,
        auth_session: Annotated[AuthSession, Depends(get_auth_session)],
    ) -> User:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            _check_csrf(request, auth_session)

        permissions = {
            permission.permission_key
            for role in auth_session.user.roles
            for permission in role.permissions
        }
        if permission_key not in permissions:
            db.add(
                _audit(
                    request,
                    action=f"authorization.denied:{permission_key}",
                    outcome="denied",
                    actor_user_id=auth_session.user_id,
                )
            )
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission_denied")
        return auth_session.user

    return permission_guard


@router.post("/login")
async def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> dict[str, object]:
    settings = get_settings()
    statement = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.username == credentials.username)
        .with_for_update()
    )
    user = (await db.execute(statement)).scalar_one_or_none()
    now = datetime.now(UTC)

    if user is None:
        try:
            password_hasher.verify(dummy_password_hash, credentials.password)
        except VerifyMismatchError:
            pass
        db.add(
            _audit(
                request,
                action="authentication.login",
                outcome="failure",
                resource_id=credentials.username,
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if not user.is_active or _is_locked(user, now):
        db.add(
            _audit(
                request,
                action="authentication.login",
                outcome="denied",
                actor_user_id=user.id,
                resource_id=user.username,
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    try:
        password_valid = password_hasher.verify(user.password_hash, credentials.password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        password_valid = False

    if not password_valid:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_lockout_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        db.add(
            _audit(
                request,
                action="authentication.login",
                outcome="failure",
                actor_user_id=user.id,
                resource_id=user.username,
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    user.failed_login_attempts = 0
    user.locked_until = None
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=settings.session_ttl_hours)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=_digest(session_token),
            csrf_token_hash=_digest(csrf_token),
            expires_at=expires_at,
        )
    )
    db.add(
        _audit(
            request,
            action="authentication.login",
            outcome="success",
            actor_user_id=user.id,
            resource_id=user.username,
        )
    )
    await db.commit()

    secure_cookie = settings.environment.lower() != "development"
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=False,
        secure=secure_cookie,
        samesite="strict",
        path="/",
    )
    return {
        "user": {"id": str(user.id), "username": user.username},
        "csrf_token": csrf_token,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/me")
async def current_user(
    request: Request,
    db: DbSession,
    auth_session: Annotated[AuthSession, Depends(get_auth_session)],
) -> dict[str, object]:
    user = auth_session.user
    db.add(
        _audit(
            request,
            action="identity.profile.read",
            outcome="success",
            actor_user_id=user.id,
            resource_id=str(user.id),
        )
    )
    await db.commit()
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "roles": sorted(role.name for role in user.roles),
        "permissions": sorted(
            permission.permission_key for role in user.roles for permission in role.permissions
        ),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    auth_session: Annotated[AuthSession, Depends(get_auth_session)],
) -> Response:
    _check_csrf(request, auth_session)
    auth_session.revoked_at = datetime.now(UTC)
    db.add(
        _audit(
            request,
            action="authentication.logout",
            outcome="success",
            actor_user_id=auth_session.user_id,
        )
    )
    await db.commit()
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/", samesite="strict")
    response.delete_cookie(settings.csrf_cookie_name, path="/", samesite="strict")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/users")
async def list_users(
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.users.read"))],
) -> list[dict[str, object]]:
    statement = select(User).options(selectinload(User.roles)).order_by(User.username)
    users = (await db.execute(statement)).scalars().unique().all()
    db.add(
        _audit(
            request,
            action="identity.users.read",
            outcome="success",
            actor_user_id=current.id,
        )
    )
    await db.commit()
    return [
        {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "roles": sorted(role.name for role in user.roles),
            "is_active": user.is_active,
        }
        for user in users
    ]
