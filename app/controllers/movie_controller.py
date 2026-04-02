"""
Movie controller — thin API layer for direct movie endpoints.
All business logic is delegated to MovieService.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_config, get_db
from app.schemas.movie import (
    MovieDetail,
    MovieSearchResponse,
    MovieSearchResult,
)
from app.services.movie_service import MovieService

router = APIRouter(prefix="/movies", tags=["Movies"])


def _get_movie_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_config),
) -> MovieService:
    """Dependency: inject MovieService with its dependencies."""
    return MovieService(session=db, settings=settings)


@router.get(
    "/search",
    response_model=MovieSearchResponse,
    summary="Search movies by title or keywords",
)
async def search_movies(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(default=1, ge=1, description="Page number"),
    service: MovieService = Depends(_get_movie_service),
) -> MovieSearchResponse:
    """Search TMDB for movies matching the query."""
    return await service.search_movies(query=q, page=page)


@router.get(
    "/{imdb_id}",
    response_model=MovieDetail,
    summary="Get movie details by IMDb ID",
)
async def get_movie_detail(
    imdb_id: str,
    service: MovieService = Depends(_get_movie_service),
) -> MovieDetail:
    """Get full details for a specific movie."""
    return await service.get_movie_detail(imdb_id=imdb_id)
