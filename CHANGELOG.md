# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Pinecone** optional index for movie-document RAG: bounded chunking, metadata flags (`has_overview`, `overview_truncated`, `ingested_from`, `text_length`), `imdb_id` deduplication after query, heuristic rerank + score floor before prompt assembly.
- **OpenAI** for LangGraph chat steps when `OPENAI_API_KEY` is set; comma-separated **`OPENAI_CHAT_MODEL_TIERS`** for cheap-to-expensive synthesis. Ollama remains available when OpenAI is not configured (including Redis embedding path unchanged).
- **Template + rule-based** prompt optimization (`app/services/agent/prompt_optimization.py`) replacing LLM-only pre-optimization; history and retrieved context threaded into `OPTIMIZED_TASK_TEMPLATE`.
- **Graph order**: `pinecone_context` → `context_builder` → `tools_decision` → `synthesizer` → `eval_gate` → `quality_eval`.
- **Quality**: `QUALITY_GOOD_ENOUGH` (default 8) stops escalation when met; `QUALITY_MIN_SCORE` remains the ship floor.
- **Observability checkpoints** per turn: `retrieval_score`, `tool_used`, `eval_score`, `retry_count`; structured JSON logs and rolling **escalation rate** (`record_graph_completion` / `log_agent_checkpoint`).
- **Hybrid tools**: `search_movies` / `get_movie_details` try Pinecone first, fall back to OMDb and upsert into Pinecone when configured.
- **`movie_service`**: after SQL cache miss + OMDb fetch, upsert full detail into Pinecone when available.

### Changed

- Semantic **Redis** Q&A cache behavior unchanged (still uses Ollama embeddings).
