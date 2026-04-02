"""
OMDb API async HTTP client.
Encapsulates all OMDb API interactions.
"""

import httpx

from app.core.config import Settings
from app.core.exceptions import ExternalAPIException
from app.core.logging import get_logger

logger = get_logger(__name__)


class OMDbClient:
    """Async client for OMDb API."""

    def __init__(self, settings: Settings):
        self._api_key = settings.OMDB_API_KEY
        self._base_url = settings.OMDB_BASE_URL
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=15.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get(self, params: dict) -> dict:
        """Make a GET request to OMDb."""
        client = await self._get_client()
        params["apikey"] = self._api_key
        try:
            response = await client.get("/", params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("Response") == "False":
                return {"Error": data.get("Error")}
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"OMDb API error: {e.response.status_code}")
            raise ExternalAPIException("OMDb", str(e.response.status_code))
        except httpx.RequestError as e:
            logger.error(f"OMDb connection error: {e}")
            raise ExternalAPIException("OMDb", "Connection failed")

    # ── Public Methods ───────────────────────────────

    async def search_movies(self, query: str, page: int = 1) -> dict:
        """
        Search for movies by title.
        Returns: { total_results, page, results: [...] }
        """
        data = await self._get({"s": query, "page": page, "type": "movie"})
        
        if "Error" in data:
            return {"total_results": 0, "page": page, "results": []}

        results = [self._format_movie_brief(m) for m in data.get("Search", [])]
        
        return {
            "total_results": int(data.get("totalResults", 0)),
            "page": page,
            "results": results,
        }

    async def get_movie(self, imdb_id: str) -> dict | None:
        """Get full details for a specific movie."""
        data = await self._get({"i": imdb_id, "plot": "full"})
        
        if "Error" in data:
            return None
            
        return self._format_movie_detail(data)

    # ── Formatters ───────────────────────────────────

    @staticmethod
    def _format_movie_brief(raw: dict) -> dict:
        return {
            "imdb_id": raw.get("imdbID"),
            "title": raw.get("Title", "Unknown"),
            "release_date": raw.get("Year"),
            "poster_url": raw.get("Poster") if raw.get("Poster") != "N/A" else None,
        }

    @staticmethod
    def _format_movie_detail(raw: dict) -> dict:
        # Try to parse imdbRating
        rating = raw.get("imdbRating")
        vote_average = None
        if rating and rating != "N/A":
            try:
                vote_average = float(rating)
            except ValueError:
                pass
                
        # Try to parse imdbVotes
        votes = raw.get("imdbVotes")
        vote_count = None
        if votes and votes != "N/A":
            try:
                # Votes have commas e.g. "1,234,567"
                vote_count = int(votes.replace(",", ""))
            except ValueError:
                pass

        # Parse runtime "148 min"
        runtime_str = raw.get("Runtime")
        runtime = None
        if runtime_str and runtime_str != "N/A":
            try:
                runtime = int(runtime_str.split()[0])
            except (ValueError, IndexError):
                pass

        # Parse genres
        genres_str = raw.get("Genre", "")
        genres = [g.strip() for g in genres_str.split(",")] if genres_str and genres_str != "N/A" else []

        poster = raw.get("Poster")

        return {
            "imdb_id": raw.get("imdbID"),
            "title": raw.get("Title", "Unknown"),
            "overview": raw.get("Plot") if raw.get("Plot") != "N/A" else "",
            "release_date": raw.get("Released") if raw.get("Released") != "N/A" else raw.get("Year"),
            "poster_url": poster if poster != "N/A" else None,
            "backdrop_url": None, # OMDb does not provide backdrop images
            "vote_average": vote_average,
            "vote_count": vote_count,
            "genres": genres,
            "runtime": runtime,
        }
