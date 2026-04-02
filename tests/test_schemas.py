"""
Tests for Pydantic schemas validation.
"""

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.movie import MovieSearchResult, MovieDetail


def test_chat_request_valid():
    """Test valid chat request."""
    req = ChatRequest(message="Tell me about The Matrix")
    assert req.message == "Tell me about The Matrix"
    assert req.conversation_id is None


def test_chat_request_with_conversation_id():
    """Test chat request with existing conversation."""
    req = ChatRequest(message="What else?", conversation_id="abc-123")
    assert req.conversation_id == "abc-123"


def test_chat_request_empty_message_rejected():
    """Test that empty messages are rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_chat_response():
    """Test chat response schema."""
    resp = ChatResponse(
        conversation_id="xyz-789",
        reply="The Matrix is a 1999 sci-fi film.",
        tool_calls_made=["search_movies"],
    )
    assert resp.conversation_id == "xyz-789"
    assert len(resp.tool_calls_made) == 1


def test_movie_search_result():
    """Test movie search result schema."""
    result = MovieSearchResult(
        imdb_id="tt0137523",
        title="Fight Club",
        vote_average=8.4,
    )
    assert result.imdb_id == "tt0137523"
    assert result.overview is None  # Optional


def test_movie_detail_with_genres():
    """Test movie detail with full data."""
    detail = MovieDetail(
        imdb_id="tt1375666",
        title="Inception",
        overview="A thief who steals corporate secrets...",
        release_date="2010-07-16",
        vote_average=8.4,
        vote_count=35000,
        genres=["Action", "Science Fiction", "Adventure"],
        runtime=148,
    )
    assert len(detail.genres) == 3
    assert detail.runtime == 148
