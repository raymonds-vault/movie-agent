# Redis Semantic Cache Issue Report

## Overview
During the implementation of the Redis Vector Database (Semantic Cache) for the `MovieAgent`, several cascading issues occurred that blocked data from successfully inserting into the database, silently swallowed the cache hit lookups, and crashed the `uvicorn` instance.

This log details the exact timeline of those issues and the resulting fixes applied to normalize the application.

### 1. Missing Dependencies & Module Errors
- **Symptom:** Starting the server raised a `ModuleNotFoundError: No module named 'redis'`.
- **Fix:** Ran `pip install redis` within the `venv` to pull down `redis-7.4.0`.

### 2. Broken RediSearch API Abstractions
- **Symptom:** Starting the server raised `ModuleNotFoundError: No module named 'redis.commands.search.indexDefinition'`.
- **Root Cause:** Due to recent restructuring in the `redis-py` library, certain high-level search builder utilities were removed or reorganized.
- **Fix:** Completely detached from the RediSearch `Query` / `IndexDefinition` builder APIs inside `app/core/redis.py` and `app/repositories/redis_repo.py`. We swapped the logic to construct schema constraints actively using the raw asynchronous string function: `client.execute_command("FT.CREATE", ...)`.

### 3. Missing Local Embeddings Model
- **Symptom:** `ChatService` experienced silent `Semantic cache error` swallows natively logged as `model "nomic-embed-text" not found, try pulling it first (status code: 404)`.
- **Fix:** Executed `ollama pull nomic-embed-text` directly on the host machine to make the model accessible for generating the feature arrays.

### 4. Vector Dimension Scaling Mismatch
- **Symptom:** The cache remained empty in the database (`Keys: []`) despite no Python runtime errors.
- **Root Cause:** The `execute_command("FT.CREATE")` was hardcoded to enforce a `384` dimensional vector field natively into Redis (`DIM 384`). However, the `nomic-embed-text` model embeds **`768`** dimensions. Because of this scale mismatch, RediSearch actively intercepted every `hset` mapping at the socket level and discarded the inserts silently with a `Vector size doesn't match the index size` backend error.
- **Fix:** 
    1. Dropped the broken redis index (`FT.DROPINDEX idx:movies`).
    2. Modified `app/core/redis.py` to natively define `DIM 768`.

### 5. Non-Deterministic Order Indexing Bug
- **Symptom:** `ValueError: could not convert string to float: b'prompt response string'`
- **Root Cause:** When `FT.SEARCH` successfully found a semantic cache hit natively, the `redis-py` binding returned the fields sequentially as a flattened string list (e.g. `[b"score", b"0.1", b"response", b"my string"]`). The lookup logic originally hardcoded `score = float(res[2][3])`, blindly assuming the score would uniformly land in the fourth slot. When Redis returned the elements out of order, it crashed the server logic.
- **Fix:** Dropped the linear array slicing and mapped the `res[2]` output directly into a Python associative dictionary loop before trying to dynamically `doc.get("score")`.

--- 
**Current Status:** Resolved. The API perfectly utilizes Vector Nearest Neighbor lookups in the caching wrapper spanning both Rest API and WebSockets.
