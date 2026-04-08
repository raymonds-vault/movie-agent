"""Initialize Firebase Admin SDK for ID token verification."""

from __future__ import annotations

import json
import logging

import firebase_admin
from firebase_admin import credentials

from app.core.config import Settings

logger = logging.getLogger(__name__)


def init_firebase(settings: Settings) -> None:
    """
    Idempotent: call on app startup when real Firebase verification is required.
    Skips when auth bypass is active or credentials are absent.
    """
    if not settings.AUTH_ENABLED or settings.AUTH_DEV_BYPASS:
        logger.info("Firebase Admin: skipped (auth bypass or AUTH_ENABLED=false)")
        return
    if firebase_admin._apps:
        return
    cred_path = (settings.FIREBASE_CREDENTIALS_PATH or "").strip()
    cred_json = (settings.FIREBASE_CREDENTIALS_JSON or "").strip()
    if cred_path:
        cred = credentials.Certificate(cred_path)
    elif cred_json:
        cred = credentials.Certificate(json.loads(cred_json))
    else:
        logger.warning(
            "Firebase Admin: no FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON; "
            "token verification will fail until configured."
        )
        return
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK initialized")
