"""
FastAPI dependency injection functions.
These are the glue between the API layer and the service layer.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DEV_FIREBASE_UID, claims_to_user_fields, verify_firebase_id_token
from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.repositories.user_repo import UserRepository

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closed after request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_config() -> Settings:
    """Return the cached settings instance."""
    return get_settings()


def _auth_bypass(settings: Settings) -> bool:
    return not settings.AUTH_ENABLED or settings.AUTH_DEV_BYPASS


async def _ensure_bypass_user(session: AsyncSession) -> User:
    repo = UserRepository(session)
    existing = await repo.get_by_firebase_uid(DEV_FIREBASE_UID)
    if existing:
        return existing
    return await repo.upsert_from_claims(
        firebase_uid=DEV_FIREBASE_UID,
        email="dev@localhost",
        display_name="Dev User",
        photo_url=None,
        email_verified=True,
    )


async def resolve_user_from_id_token(
    session: AsyncSession,
    settings: Settings,
    id_token: str | None,
) -> User:
    """Resolve or create User from Firebase ID token (or dev bypass user)."""
    if _auth_bypass(settings):
        return await _ensure_bypass_user(session)
    if not id_token or not str(id_token).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing id_token",
        )
    try:
        claims = await verify_firebase_id_token(id_token.strip(), settings)
        fields = claims_to_user_fields(claims)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None
    repo = UserRepository(session)
    return await repo.upsert_from_claims(**fields)


async def resolve_chat_user_from_id_token(
    session: AsyncSession,
    settings: Settings,
    id_token: str | None,
) -> User | None:
    """
    For chat/WebSocket: anonymous when no token (production).
    Invalid token still raises HTTPException.
    """
    if _auth_bypass(settings):
        return await _ensure_bypass_user(session)
    if not id_token or not str(id_token).strip():
        return None
    try:
        claims = await verify_firebase_id_token(id_token.strip(), settings)
        fields = claims_to_user_fields(claims)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None
    repo = UserRepository(session)
    return await repo.upsert_from_claims(**fields)


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_config),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User | None:
    """Bearer token optional: None when unauthenticated (anonymous chat)."""
    if _auth_bypass(settings):
        return await _ensure_bypass_user(db)
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    return await resolve_user_from_id_token(db, settings, credentials.credentials)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_config),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    """Bearer Firebase ID token for HTTP routes."""
    if _auth_bypass(settings):
        return await _ensure_bypass_user(db)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return await resolve_user_from_id_token(db, settings, credentials.credentials)
