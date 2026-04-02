"""
Redis core module for connection management and RediSearch index initialization.
"""

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Using a global client for the app lifecycle
redis_client: redis.Redis | None = None

async def init_redis():
    """Initialize the Redis connection and search index."""
    global redis_client
    settings = get_settings()
    
    logger.info(f"Connecting to Redis at {settings.REDIS_URL}...")
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    
    # Initialize the index
    await setup_redis_index(redis_client)

async def close_redis():
    """Close the Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.aclose()


async def setup_redis_index(client: redis.Redis):
    """
    Creates the RediSearch index for vector-based movie caching using `execute_command`.
    Uses HNSW for the vector search with DIM 384.
    """
    index_name = "idx:movies"
    try:
        await client.execute_command(
            "FT.CREATE", index_name,
            "ON", "HASH",
            "PREFIX", "1", "movie:",
            "SCHEMA",
            "query", "TEXT",
            "embedding", "VECTOR", "HNSW", "6",
            "TYPE", "FLOAT32",
            "DIM", "768",
            "DISTANCE_METRIC", "COSINE"
        )
        logger.info(f"Successfully created Redis index {index_name}")
    except Exception as e:
        logger.info(f"Index may already exist or error: {e}")
