"""
Projection writer for Redis CQRS read models.
"""

from app.core.logging import get_logger
from app.repositories.redis_repo import RedisProjectionRepository

logger = get_logger(__name__)


class ProjectionService:
    def __init__(self, repo: RedisProjectionRepository | None):
        self._repo = repo

    async def update_conversation_projection(
        self,
        conversation_id: str,
        *,
        summary_text: str | None,
        latest_run_id: str | None,
        latest_quality_score: int | None,
    ) -> None:
        if not self._repo:
            return
        try:
            await self._repo.set_conversation_projection(
                conversation_id,
                summary_text=summary_text,
                latest_run_id=latest_run_id,
                latest_quality_score=latest_quality_score,
            )
        except Exception as e:
            logger.warning("Projection write (conversation) failed: %s", e)

    async def update_run_projection(
        self,
        run_id: str,
        *,
        conversation_id: str,
        status: str,
        quality_score: int | None,
        tools: list[str] | None = None,
    ) -> None:
        if not self._repo:
            return
        try:
            await self._repo.set_run_projection(
                run_id,
                conversation_id=conversation_id,
                status=status,
                quality_score=quality_score,
                tools=tools,
            )
        except Exception as e:
            logger.warning("Projection write (run) failed: %s", e)

    async def get_conversation_projection(self, conversation_id: str) -> dict[str, str] | None:
        if not self._repo:
            return None
        try:
            return await self._repo.get_conversation_projection(conversation_id)
        except Exception as e:
            logger.warning("Projection read failed: %s", e)
            return None
