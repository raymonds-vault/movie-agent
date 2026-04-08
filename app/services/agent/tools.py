"""
LangChain tools for the movie agent.
Pinecone-first retrieval with OMDb fallback; upserts into Pinecone when configured.
"""

from __future__ import annotations

from langchain_core.tools import tool

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.pinecone_movie_rag import get_pinecone_movie_rag
from app.utils.omdb_client import OMDbClient

logger = get_logger(__name__)

_omdb_client: OMDbClient | None = None


def _get_omdb_client() -> OMDbClient:
    global _omdb_client
    if _omdb_client is None:
        _omdb_client = OMDbClient(get_settings())
    return _omdb_client


def set_omdb_client(client: OMDbClient) -> None:
    global _omdb_client
    _omdb_client = client


def _format_omdb_search_line(movie: dict) -> str:
    year = movie.get("release_date", "N/A")
    return f"• **{movie['title']}** ({year}) [IMDb ID: {movie.get('imdb_id')}]"


@tool
async def search_movies(query: str) -> str:
    """
    Search for movies by title or keywords.
    Use this when users ask about finding a movie, looking up a movie by name,
    or searching for movies related to a topic.

    Args:
        query: The movie title or keywords to search for.

    Returns:
        Formatted string with search results including movie titles, years, and IMDb IDs.
    """
    settings = get_settings()
    rag = get_pinecone_movie_rag(settings)

    if rag.available:
        try:
            hits, best = await rag.query_movies(query_text=query, history_hint="")
            if hits and best is not None:
                lines = [
                    f"🔍 Vector DB matches (top relevance):\n",
                ]
                seen: set[str] = set()
                for h in hits:
                    if h.imdb_id in seen:
                        continue
                    seen.add(h.imdb_id)
                    title = str(h.metadata.get("title", "") or h.imdb_id)
                    lines.append(
                        f"• **{title}** [IMDb ID: {h.imdb_id}] (score={h.score:.3f})\n  {h.text[:400]}{'…' if len(h.text) > 400 else ''}"
                    )
                lines.append(
                    "\n_Use `get_movie_details` with an IMDb ID for full facts if needed._"
                )
                return "\n".join(lines)
        except Exception as e:
            logger.warning("Pinecone search path failed, using OMDb: %s", e)

    client = _get_omdb_client()
    results = await client.search_movies(query)

    if not results.get("results"):
        return f"No movies found for '{query}'. Try a different search term."

    lines = [f"🔍 Found {results.get('total_results')} results for '{query}':\n"]
    seen_ids: set[str] = set()
    rag = get_pinecone_movie_rag(settings)
    for movie in results["results"][:8]:
        imdb_id = movie.get("imdb_id")
        if imdb_id and imdb_id in seen_ids:
            continue
        if imdb_id:
            seen_ids.add(imdb_id)
        lines.append(_format_omdb_search_line(movie))
        if rag.available and imdb_id:
            try:
                await rag.upsert_movie_record(
                    imdb_id=imdb_id,
                    title=movie.get("title", "Unknown"),
                    release_date=str(movie.get("release_date") or ""),
                    genres=[],
                    overview="",
                )
            except Exception as e:
                logger.debug("Pinecone upsert (search brief) skipped: %s", e)

    return "\n".join(lines)


@tool
async def get_movie_details(imdb_id: str) -> str:
    """
    Get comprehensive details about a specific movie using its IMDb ID.
    Use this when users want more information about a specific movie
    that was found via search or mentioned by IMDb ID.

    Args:
        imdb_id: The IMDb ID of the movie (e.g. tt1285016).

    Returns:
        Formatted string with full movie details including genres, runtime, rating, and overview.
    """
    settings = get_settings()
    rag = get_pinecone_movie_rag(settings)

    if rag.available:
        try:
            hit = await rag.fetch_by_imdb_id(imdb_id)
            if hit and hit.text.strip():
                title = str(hit.metadata.get("title", "") or "Unknown")
                return (
                    f"🎬 **{title}** (from vector store)\n\n"
                    f"{hit.text[:6000]}\n\n"
                    f"_IMDb ID: {imdb_id}_"
                )
        except Exception as e:
            logger.warning("Pinecone fetch failed for %s: %s", imdb_id, e)

    client = _get_omdb_client()
    movie = await client.get_movie(imdb_id)

    if not movie:
        return f"Could not find details for movie with ID {imdb_id}."

    if rag.available:
        try:
            await rag.upsert_movie_record(
                imdb_id=imdb_id,
                title=movie["title"],
                release_date=str(movie.get("release_date") or ""),
                genres=movie.get("genres") or [],
                overview=str(movie.get("overview") or ""),
            )
        except Exception as e:
            logger.warning("Pinecone upsert after OMDb failed: %s", e)

    genres = ", ".join(movie.get("genres", [])) or "N/A"
    runtime = movie.get("runtime")
    runtime_str = f"{runtime} min" if runtime else "N/A"
    year = movie.get("release_date", "N/A")

    return (
        f"🎬 **{movie['title']}** ({year})\n"
        f"📊 Rating: ⭐ {movie.get('vote_average', 'N/A')}/10 "
        f"({movie.get('vote_count', 0):,} votes)\n"
        f"🎭 Genres: {genres}\n"
        f"⏱️ Runtime: {runtime_str}\n"
        f"📝 Overview: {movie.get('overview', 'No description available.')}\n"
    )


ALL_TOOLS = [search_movies, get_movie_details]
