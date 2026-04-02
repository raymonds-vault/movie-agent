"""
LangChain tools for the movie agent.
Each tool wraps an OMDb API call and returns formatted text for the LLM.
"""

from langchain_core.tools import tool

from app.core.config import get_settings
from app.utils.omdb_client import OMDbClient

# Lazy-initialized shared client
_omdb_client: OMDbClient | None = None


def _get_omdb_client() -> OMDbClient:
    """Get or create an OMDbClient instance for tools."""
    global _omdb_client
    if _omdb_client is None:
        _omdb_client = OMDbClient(get_settings())
    return _omdb_client


def set_omdb_client(client: OMDbClient) -> None:
    """Allow injection of an OMDbClient (for testing or lifecycle management)."""
    global _omdb_client
    _omdb_client = client


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
    client = _get_omdb_client()
    results = await client.search_movies(query)

    if not results.get("results"):
        return f"No movies found for '{query}'. Try a different search term."

    lines = [f"🔍 Found {results.get('total_results')} results for '{query}':\n"]
    for movie in results["results"][:8]:  # Top 8 results
        year = movie.get("release_date", "N/A")
        lines.append(
            f"• **{movie['title']}** ({year}) [IMDb ID: {movie.get('imdb_id')}]"
        )

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
    client = _get_omdb_client()
    movie = await client.get_movie(imdb_id)
    
    if not movie:
        return f"Could not find details for movie with ID {imdb_id}."

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

# Export all tools as a list for easy agent registration
ALL_TOOLS = [search_movies, get_movie_details]
