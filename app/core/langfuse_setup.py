"""
Apply Langfuse client environment variables from Settings.

The Langfuse Python SDK reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST.
"""

import os

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _warn_if_otlp_endpoint_missing(base_url: str) -> None:
    """
    SDK v4 exports via OTLP HTTP to ``/api/public/otel/v1/traces``.
    Langfuse server v2 returns 404 there — traces never appear (silent failure after flush).
    """
    path = "/api/public/otel/v1/traces"
    url = base_url.rstrip("/") + path
    try:
        r = httpx.get(url, timeout=3.0)
    except httpx.RequestError as e:
        logger.warning(
            "Langfuse OTLP probe: cannot reach %s (%s). Tracing will not work until the server is up.",
            url,
            e,
        )
        return
    if r.status_code == 404:
        logger.error(
            "Langfuse at %s is incompatible with the Python SDK: GET %s returned 404. "
            "You are running Langfuse v2; SDK v4 needs Langfuse v3+ (OpenTelemetry ingestion). "
            "From the project root run: docker compose up -d — default UI is http://localhost:3001 "
            "(see LANGFUSE_WEB_PORT). Set LANGFUSE_HOST to that URL and use API keys from the v3 project.",
            base_url,
            url,
        )


def configure_langfuse(settings: Settings) -> None:
    """Set os.environ for the Langfuse SDK when tracing is enabled."""
    if not settings.langfuse_configured:
        # Do not overwrite keys if user manages env externally; clear only our flags if disabled
        return

    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY.strip()
    os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY.strip()
    host = settings.LANGFUSE_HOST.strip() or "http://localhost:3000"
    # SDK v4 reads LANGFUSE_BASE_URL first; LANGFUSE_HOST is deprecated but still supported.
    os.environ["LANGFUSE_HOST"] = host
    os.environ["LANGFUSE_BASE_URL"] = host

    _warn_if_otlp_endpoint_missing(host)

    # CallbackHandler calls ``get_client(public_key=...)``. That looks up a registered
    # ``LangfuseResourceManager``; env vars alone do not register it — without this,
    # the SDK logs "No Langfuse client with public key ... has been initialized" and skips tracing.
    from langfuse import Langfuse

    Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY.strip(),
        secret_key=settings.LANGFUSE_SECRET_KEY.strip(),
        base_url=host,
    )

    logger.info(
        "Langfuse observability enabled (host=%s, project=%s)",
        host,
        settings.LANGFUSE_PROJECT_NAME,
    )
