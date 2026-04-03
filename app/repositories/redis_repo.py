"""
Redis repository for vector-based movie caching.
"""

import json
import struct
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)


def pack_vector(embedding: list[float]) -> bytes:
    """Pack a list of floats into a byte array for RediSearch."""
    return struct.pack(f"{len(embedding)}f", *embedding)


class RedisMovieRepository:
    """Data access abstraction for Redis Vector Search."""

    def __init__(self, client: Redis):
        self.client = client
        self.index_name = "idx:movies"

    async def store_query(
        self,
        query: str,
        response: str,
        embedding: list[float],
        *,
        user_scope: str | None = None,
        context_hash: str | None = None,
        tool_context: str | None = None,
        confidence: float | None = None,
    ) -> str | None:
        """
        Store the search query, embedding, and LLM response in Redis as a HASH.
        """
        # The user requested f"movie:{hash(query)}" as the key.
        key = f"movie:{hash((query, user_scope or '', context_hash or '', tool_context or ''))}"
        
        mapping = {
            "query": query,
            "response": response,
            "embedding": pack_vector(embedding),
            "user_scope": user_scope or "",
            "context_hash": context_hash or "",
            "tool_context": tool_context or "",
            "confidence": str(confidence if confidence is not None else ""),
        }
        
        try:
            await self.client.hset(key, mapping=mapping)
            await self.client.expire(key, 86400) # Optional cache TTL
            return key
        except Exception as e:
            logger.error(f"Failed to upsert semantic cache in Redis for {key}: {e}")
            return None

    async def search_similar(self, query_str: str, query_vector: list[float], k: int = 1) -> list[Any]:
        """
        Perform semantic cache search.
        Matches returning: [count, key, [field, val...]]
        """
        try:
            packed_vec = pack_vector(query_vector)

            # execute_command format directly from user snippet
            res = await self.client.execute_command(
                "FT.SEARCH", self.index_name,
                f"*=>[KNN {k} @embedding $vec AS score]",
                "PARAMS", "2", "vec", packed_vec,
                "SORTBY", "score",
                "RETURN", "8", "response", "score", "query", "user_scope", "context_hash", "tool_context", "confidence",
                "DIALECT", "2"
            )
            
            return res
        except Exception as e:
            logger.error(f"Error during Redis semantic search: {e}")
            return []


class RedisProjectionRepository:
    """CQRS-style read projections for fast context and run summaries."""

    def __init__(self, client: Redis):
        self.client = client

    async def set_conversation_projection(
        self,
        conversation_id: str,
        *,
        summary_text: str | None,
        latest_run_id: str | None,
        latest_quality_score: int | None,
    ) -> None:
        key = f"proj:conversation:{conversation_id}:context"
        mapping = {
            "summary_text": summary_text or "",
            "latest_run_id": latest_run_id or "",
            "latest_quality_score": "" if latest_quality_score is None else str(latest_quality_score),
        }
        await self.client.hset(key, mapping=mapping)
        await self.client.expire(key, 60 * 60 * 24)

    async def get_conversation_projection(self, conversation_id: str) -> dict[str, str] | None:
        key = f"proj:conversation:{conversation_id}:context"
        raw = await self.client.hgetall(key)
        if not raw:
            return None
        out: dict[str, str] = {}
        for k, v in raw.items():
            kk = k.decode() if isinstance(k, bytes) else str(k)
            vv = v.decode() if isinstance(v, bytes) else str(v)
            out[kk] = vv
        return out

    async def set_run_projection(
        self,
        run_id: str,
        *,
        conversation_id: str,
        status: str,
        quality_score: int | None,
        tools: list[str] | None = None,
    ) -> None:
        key = f"proj:run:{run_id}"
        mapping = {
            "conversation_id": conversation_id,
            "status": status,
            "quality_score": "" if quality_score is None else str(quality_score),
            "tools": json.dumps(tools or []),
        }
        await self.client.hset(key, mapping=mapping)
        await self.client.expire(key, 60 * 60 * 24)
