"""
Movie service — business logic for direct movie operations.
Wraps TMDB client with caching and data transformation.
"""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_ollama import OllamaEmbeddings

from app.core.config import Settings
from app.core.exceptions import ExternalAPIException
from app.core.logging import get_logger
from app.repositories.movie_repo import MovieRepository
from app.repositories.redis_repo import RedisMovieRepository
import app.core.redis as redis_core

from app.schemas.movie import (
    MovieDetail,
    MovieSearchResponse,
    MovieSearchResult,
)
from app.utils.omdb_client import OMDbClient

logger = get_logger(__name__)


class MovieService:
    """
    Handles movie-related business logic:
    - Search with caching
    - Detail retrieval with caching
    """

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._movie_repo = MovieRepository(session)
        self._omdb = OMDbClient(settings)

    async def search_movies(self, query: str, page: int = 1) -> MovieSearchResponse:
        """Search movies via OMDb."""
        if not self._settings.omdb_configured:
            raise ExternalAPIException("OMDb", "OMDB_API_KEY not configured")

        # Fallback to OMDb
        data = await self._omdb.search_movies(query, page)
        results = [MovieSearchResult(**m) for m in data["results"]]

        return MovieSearchResponse(
            query=query,
            total_results=data["total_results"],
            page=data["page"],
            results=results,
        )

    async def get_movie_detail(self, imdb_id: str) -> MovieDetail:
        """Get movie details, with cache-first strategy."""
        if not self._settings.omdb_configured:
            raise ExternalAPIException("OMDb", "OMDB_API_KEY not configured")

        # Check SQL cache first
        cached = await self._movie_repo.get_cached(imdb_id)
        if cached:
            logger.debug(f"Cache hit for movie {imdb_id}")
            import json
            genres = json.loads(cached.genres) if cached.genres else []
            return MovieDetail(
                imdb_id=cached.imdb_id,
                title=cached.title,
                overview=cached.overview,
                release_date=cached.release_date,
                poster_url=cached.poster_path,
                backdrop_url=cached.backdrop_path,
                vote_average=cached.vote_average,
                vote_count=cached.vote_count,
                genres=genres,
                runtime=cached.runtime,
            )

        # Fetch from OMDb and cache
        data = await self._omdb.get_movie(imdb_id)
        
        if not data:
             raise ExternalAPIException("OMDb", "Movie not found")

        # Cache the result
        await self._movie_repo.upsert(
            imdb_id=imdb_id,
            data={
                "title": data["title"],
                "overview": data.get("overview"),
                "release_date": data.get("release_date"),
                "poster_path": data.get("poster_url"),
                "backdrop_path": data.get("backdrop_url"),
                "vote_average": data.get("vote_average"),
                "vote_count": data.get("vote_count"),
                "genres": data.get("genres", []),
                "runtime": data.get("runtime"),
            },
        )

        return MovieDetail(**data)
