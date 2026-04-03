"""Flush Langfuse OTLP export buffer after a graph run (avoids missing traces on short requests)."""

from app.core.logging import get_logger

logger = get_logger(__name__)


def flush_langfuse() -> None:
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as e:
        logger.debug("Langfuse flush skipped: %s", e)
