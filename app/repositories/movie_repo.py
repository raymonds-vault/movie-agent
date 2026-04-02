"""
Movie cache repository.
"""

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.movie import CachedMovie
from app.repositories.base import BaseRepository

# Cache TTL: 24 hours
CACHE_TTL = timedelta(hours=24)


class MovieRepository(BaseRepository[CachedMovie]):
    """Data access for cached movie data."""

    def __init__(self, session: AsyncSession):
        super().__init__(CachedMovie, session)

    async def get_cached(self, imdb_id: str) -> CachedMovie | None:
        """Get a cached movie if it's still fresh."""
        stmt = select(CachedMovie).where(CachedMovie.imdb_id == imdb_id)
        result = await self._session.execute(stmt)
        movie = result.scalar_one_or_none()

        if movie and self._is_stale(movie):
            return None  # Treat stale cache as miss
        return movie

    async def upsert(self, imdb_id: str, data: dict) -> CachedMovie:
        """Insert or update a cached movie."""
        existing = await self.get_by_id(imdb_id)
        if existing:
            return await self.update(existing, **data)

        # Handle genres as JSON string
        if "genres" in data and isinstance(data["genres"], list):
            data["genres"] = json.dumps(data["genres"])

        return await self.create(imdb_id=imdb_id, **data)

    @staticmethod
    def _is_stale(movie: CachedMovie) -> bool:
        """Check if cached data has expired."""
        if not movie.updated_at:
            return True
        now = datetime.now(timezone.utc)
        age = now - movie.updated_at.replace(tzinfo=timezone.utc)
        return age > CACHE_TTL
