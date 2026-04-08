"""Verify Firebase ID tokens and map claims to application user fields."""

from __future__ import annotations

import asyncio

import firebase_admin.auth as firebase_auth

from app.core.config import Settings

DEV_FIREBASE_UID = "__dev_bypass__"


def verify_firebase_id_token_sync(id_token: str, settings: Settings) -> dict:
    """
    Verify a Firebase ID token and return decoded claims.
    Raises firebase_admin exceptions on failure.
    """
    if not settings.AUTH_ENABLED or settings.AUTH_DEV_BYPASS:
        raise RuntimeError("verify_firebase_id_token_sync called while auth bypass is active")
    return firebase_auth.verify_id_token(id_token)


async def verify_firebase_id_token(id_token: str, settings: Settings) -> dict:
    return await asyncio.to_thread(verify_firebase_id_token_sync, id_token, settings)


def claims_to_user_fields(claims: dict) -> dict:
    """Map Firebase token claims to UserRepository.upsert_from_claims kwargs."""
    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise ValueError("Token missing uid")
    return {
        "firebase_uid": uid,
        "email": claims.get("email"),
        "display_name": claims.get("name") or claims.get("display_name"),
        "photo_url": claims.get("picture"),
        "email_verified": bool(claims.get("email_verified", False)),
    }
