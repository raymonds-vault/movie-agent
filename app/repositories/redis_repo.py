"""
Redis repository for vector-based movie caching.
"""

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

    async def store_query(self, query: str, response: str, embedding: list[float]):
        """
        Store the search query, embedding, and LLM response in Redis as a HASH.
        """
        # The user requested f"movie:{hash(query)}" as the key.
        key = f"movie:{hash(query)}"
        
        mapping = {
            "query": query,
            "response": response,
            "embedding": pack_vector(embedding),
        }
        
        try:
            await self.client.hset(key, mapping=mapping)
            await self.client.expire(key, 86400) # Optional cache TTL
        except Exception as e:
            logger.error(f"Failed to upsert semantic cache in Redis for {key}: {e}")

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
                "RETURN", "2", "response", "score",
                "DIALECT", "2"
            )
            
            return res
        except Exception as e:
            logger.error(f"Error during Redis semantic search: {e}")
            return []
