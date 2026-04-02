"""
Movie-related Pydantic schemas.
"""

from pydantic import BaseModel, Field


class MovieSearchResult(BaseModel):
    """Single movie in search results."""

    imdb_id: str
    title: str
    overview: str | None = None
    release_date: str | None = None
    poster_url: str | None = None
    vote_average: float | None = None


class MovieDetail(BaseModel):
    """Full movie details."""

    imdb_id: str
    title: str
    overview: str | None = None
    release_date: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    genres: list[str] = Field(default_factory=list)
    runtime: int | None = None


class MovieSearchResponse(BaseModel):
    """Paginated movie search response."""

    query: str
    total_results: int
    page: int
    results: list[MovieSearchResult]



