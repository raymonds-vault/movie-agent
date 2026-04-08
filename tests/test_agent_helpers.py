"""Unit tests for Pinecone dedupe, heuristic rerank, and prompt optimization."""

from app.services.agent.prompt_optimization import build_optimized_prompt
from app.services.pinecone_movie_rag import RetrievalHit, dedupe_by_imdb_id, heuristic_rerank


def test_dedupe_by_imdb_id_keeps_best_score():
    hits = [
        RetrievalHit("tt1", 0.5, "a", {"title": "A"}),
        RetrievalHit("tt1", 0.8, "b", {"title": "B"}),
        RetrievalHit("tt2", 0.9, "c", {"title": "C"}),
    ]
    out = dedupe_by_imdb_id(hits)
    assert len(out) == 2
    by_id = {h.imdb_id: h for h in out}
    assert by_id["tt1"].score == 0.8
    assert by_id["tt1"].text == "b"


def test_heuristic_rerank_orders_by_overlap():
    hits = [
        RetrievalHit("tt1", 0.9, "space adventure mars", {}),
        RetrievalHit("tt2", 0.95, "cooking show", {}),
    ]
    out = heuristic_rerank(hits, "space adventure film")
    assert out[0].imdb_id == "tt1"


def test_build_optimized_prompt_includes_sections():
    t = build_optimized_prompt(
        user_query="Best sci-fi?",
        history_summary="User likes Blade Runner.",
        feedback_context="None",
        retrieved_movie_context="Title: Dune",
        raw_history=[{"role": "user", "content": "hi"}],
    )
    assert "Best sci-fi" in t
    assert "Blade Runner" in t
    assert "Dune" in t
