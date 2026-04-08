"""
Pinecone-backed movie retrieval: bounded chunking, metadata flags, dedupe, light rerank.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalHit:
    imdb_id: str
    score: float
    text: str
    metadata: dict[str, Any]


def _truncate(s: str | None, max_len: int) -> str:
    if not s:
        return ""
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def build_movie_embed_text(
    *,
    title: str,
    release_date: str | None,
    genres: list[str],
    overview: str,
    settings: Settings,
) -> tuple[str, dict[str, Any]]:
    """Single bounded chunk text + quality flags for Pinecone metadata."""
    ov = _truncate(overview, settings.MOVIE_EMBED_MAX_OVERVIEW_CHARS)
    has_overview = bool(ov)
    year = (release_date or "")[:4] if release_date else ""
    g = ", ".join(genres) if genres else ""
    parts = [
        f"Title: {title}",
        f"Year: {year}" if year else "",
        f"Genres: {g}" if g else "",
        f"Overview: {ov}" if ov else "",
    ]
    text = "\n".join(p for p in parts if p)
    flags = {
        "has_overview": has_overview,
        "overview_truncated": len((overview or "").strip()) > settings.MOVIE_EMBED_MAX_OVERVIEW_CHARS,
        "text_length": len(text),
        "ingested_from": "omdb",
    }
    return text, flags


class PineconeMovieRAG:
    """Query and upsert movie vectors; optional when Pinecone is not configured."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._embeddings: OpenAIEmbeddings | None = None
        self._index = None
        if settings.openai_configured:
            self._embeddings = OpenAIEmbeddings(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_EMBEDDING_MODEL,
            )
        if settings.pinecone_configured and self._embeddings:
            try:
                from pinecone import Pinecone

                pc = Pinecone(api_key=settings.PINECONE_API_KEY)
                self._index = pc.Index(settings.PINECONE_INDEX_NAME)
            except Exception as e:
                logger.warning("Pinecone index init failed: %s", e)
                self._index = None

    @property
    def available(self) -> bool:
        return self._index is not None and self._embeddings is not None

    async def embed_query(self, text: str) -> list[float]:
        if not self._embeddings:
            raise RuntimeError("OpenAI embeddings not configured")
        return await self._embeddings.aembed_query(text)

    async def query_movies(
        self,
        *,
        query_text: str,
        history_hint: str = "",
    ) -> tuple[list[RetrievalHit], float | None]:
        """
        Returns hits and best deduped score (None if skipped).
        """
        if not self.available:
            return [], None
        enriched = f"{history_hint.strip()}\n\n{query_text}".strip() if history_hint else query_text
        vec = await self.embed_query(enriched[:8000])
        assert self._index is not None
        try:
            res = self._index.query(
                vector=vec,
                top_k=self._settings.PINECONE_RETRIEVAL_TOP_K,
                namespace=self._settings.PINECONE_NAMESPACE,
                include_metadata=True,
            )
        except Exception as e:
            logger.error("Pinecone query failed: %s", e, exc_info=True)
            return [], None

        matches = getattr(res, "matches", None) or []
        raw_hits: list[RetrievalHit] = []
        for m in matches:
            meta = dict(m.metadata or {})
            imdb_id = str(meta.get("imdb_id", "") or "")
            score = float(m.score or 0.0)
            text = str(meta.get("text", "") or "")
            if score < self._settings.PINECONE_MIN_SCORE:
                continue
            if not imdb_id:
                continue
            raw_hits.append(RetrievalHit(imdb_id=imdb_id, score=score, text=text, metadata=meta))

        deduped = dedupe_by_imdb_id(raw_hits)
        reranked = heuristic_rerank(deduped, query_text)
        capped = reranked[: self._settings.PINECONE_MAX_UNIQUE_MOVIES]
        best = max((h.score for h in capped), default=None)
        return capped, best

    def format_context(self, hits: list[RetrievalHit]) -> str:
        if not hits:
            return ""
        lines: list[str] = []
        budget = self._settings.PINECONE_CONTEXT_MAX_CHARS
        used = 0
        for h in hits:
            block = f"### {h.imdb_id} (score={h.score:.3f})\n{h.text}\n\n"
            if used + len(block) > budget:
                rest = budget - used
                if rest > 80:
                    lines.append(block[:rest] + "…")
                break
            lines.append(block)
            used += len(block)
        return "".join(lines).strip()

    async def fetch_by_imdb_id(self, imdb_id: str) -> RetrievalHit | None:
        """Return stored chunk for an IMDb ID if present."""
        if not self.available:
            return None
        vid = f"{imdb_id}_c0"
        assert self._index is not None
        try:
            res = self._index.fetch(ids=[vid], namespace=self._settings.PINECONE_NAMESPACE)
        except Exception as e:
            logger.debug("Pinecone fetch %s: %s", imdb_id, e)
            return None
        vectors = getattr(res, "vectors", None) or {}
        rec = vectors.get(vid)
        if not rec:
            return None
        meta = dict(getattr(rec, "metadata", None) or {})
        text = str(meta.get("text", "") or "")
        if not text.strip():
            return None
        return RetrievalHit(
            imdb_id=imdb_id,
            score=1.0,
            text=text,
            metadata=meta,
        )

    async def upsert_movie_record(
        self,
        *,
        imdb_id: str,
        title: str,
        release_date: str | None,
        genres: list[str],
        overview: str,
    ) -> None:
        if not self.available:
            return
        text, flags = build_movie_embed_text(
            title=title,
            release_date=release_date,
            genres=genres,
            overview=overview,
            settings=self._settings,
        )
        if self._settings.MOVIE_MAX_CHUNKS_PER_MOVIE < 1:
            return
        vec = await self.embed_query(text)
        vid = f"{imdb_id}_c0"
        meta = {
            "imdb_id": imdb_id,
            "title": title[:500],
            "text": text[:8000],
            **{k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in flags.items()},
        }
        assert self._index is not None
        try:
            self._index.upsert(
                vectors=[{"id": vid, "values": vec, "metadata": meta}],
                namespace=self._settings.PINECONE_NAMESPACE,
            )
        except Exception as e:
            logger.warning("Pinecone upsert failed for %s: %s", imdb_id, e)


def dedupe_by_imdb_id(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Keep best score per imdb_id."""
    best: dict[str, RetrievalHit] = {}
    for h in hits:
        cur = best.get(h.imdb_id)
        if cur is None or h.score > cur.score:
            best[h.imdb_id] = h
    return sorted(best.values(), key=lambda x: x.score, reverse=True)


def heuristic_rerank(hits: list[RetrievalHit], query: str) -> list[RetrievalHit]:
    """Light lexical overlap + Pinecone score."""
    if not hits or not query.strip():
        return hits
    qtok = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not qtok:
        return hits

    def score_hit(h: RetrievalHit) -> float:
        tt = re.findall(r"[a-z0-9]+", (h.text + " " + str(h.metadata.get("title", ""))).lower())
        overlap = len(qtok & set(tt)) / max(len(qtok), 1)
        return h.score * 0.65 + overlap * 0.35

    return sorted(hits, key=score_hit, reverse=True)


_rag_singleton: PineconeMovieRAG | None = None


def get_pinecone_movie_rag(settings: Settings) -> PineconeMovieRAG:
    global _rag_singleton
    if _rag_singleton is None:
        _rag_singleton = PineconeMovieRAG(settings)
    return _rag_singleton


def reset_pinecone_movie_rag_for_tests() -> None:
    global _rag_singleton
    _rag_singleton = None
