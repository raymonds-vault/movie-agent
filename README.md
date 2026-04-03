# 🎬 Movie Agent

Movie Agent is a local-first AI movie assistant built with FastAPI + LangGraph + Ollama, with Redis semantic cache and Langfuse observability.

This README documents:
- system design and control flow
- node-by-node technical behavior
- class/function responsibilities
- packages and runtime dependencies
- screenshot-backed tracing and UI references

## Product Screenshots

### App UI (CinemaBot)
![CinemaBot UI](/home/raymond/.cursor/projects/home-raymond-Desktop-coding-ai-movie-agent/assets/Screenshot_from_2026-04-03_14-51-24-9aa84382-099a-4ce4-b3ec-afd1b040f4e6.png)

### Langfuse Trace Graph + Inputs/Outputs
![Langfuse Trace](/home/raymond/.cursor/projects/home-raymond-Desktop-coding-ai-movie-agent/assets/Screenshot_from_2026-04-03_14-51-31-db39af2e-fc53-491f-8f6e-90a62c0aca38.png)

## Overall System Design

```text
Client (React + WS)
   -> FastAPI Controllers
      -> ChatService
         -> Redis semantic cache (+ optional LLM verifier)
         -> LangGraph agent pipeline
             summarize_history
             -> optimize_prompt
             -> tools_phase <-> ToolNode(OMDb tools)
             -> synthesizer
             -> quality_eval
             -> (retry synthesizer with fallback model OR accept)
         -> persist messages + optional Redis write-back
      -> Repositories (SQLAlchemy async/MySQL)
```

### Layering
- `controllers` -> HTTP/WS transport only
- `services` -> orchestration/business logic
- `repositories` -> database access
- `services/agent` -> graph, prompts, tools, quality, tracing metadata
- `core` -> app config, logging, DB/Redis setup, Langfuse setup

## User Flow

1. User sends message from composer.
2. WebSocket `/api/v1/chat/ws` starts streaming turn.
3. `ChatService.stream_message()` optionally tries semantic cache.
4. If cache hit:
   - evaluate quality with shared quality gate
   - if acceptable: return cached answer immediately
   - else: continue to graph
5. Graph executes:
   - summarize recent history into compact memory
   - optimize prompt for low-token routing
   - run tool-calling phase and OMDb tools
   - synthesize user-facing response
   - evaluate response quality
   - if low quality and retries remain: regenerate with fallback model
6. Final response is persisted and streamed to UI.
7. Response can be regenerated from UI (same last user message, same conversation).

## Control Flow (Graph)

```text
START
  -> summarize_history
  -> optimize_prompt
  -> tools_phase
      -> if tool calls present: tools -> tools_phase
      -> else: synthesizer
  -> quality_eval
      -> if score >= QUALITY_MIN_SCORE: END
      -> else if synthesis_pass_count < MAX_SYNTHESIS_PASSES: synthesizer
      -> else: END
```

## Technical Reference: Agent Nodes

### `summarize_history(state, config)`
- File: `app/services/agent/agent.py`
- Uses: `SUMMARY_HISTORY_PROMPT` + base model
- Input: `raw_history` (recent DB messages)
- Output: `history_summary` (2-4 sentence compact memory)
- Goal: reduce prompt size and preserve context quality

### `optimize_prompt(state, config)`
- Uses: `OPTIMIZE_PRE_LLM_PROMPT`
- Inputs: `history_summary`, `user_query`, `feedback_context`
- Output: `optimized_prompt`
- Goal: convert vague follow-ups into explicit, short task instructions before tool/LLM steps

### `tools_phase(state, config)`
- Uses: `ChatOllama(...).bind_tools(ALL_TOOLS)` + `TOOLS_PHASE_SYSTEM_PROMPT`
- First iteration input: summary + optimized task + latest message
- Loops with `ToolNode(ALL_TOOLS)` while `AIMessage.tool_calls` exist
- Guard: `MAX_TOOL_PHASE_ROUNDS = 8`

### `tools` (LangGraph `ToolNode`)
- Executes registered async tools:
  - `search_movies(query)`
  - `get_movie_details(imdb_id)`
- Tool outputs are appended as `ToolMessage` into graph state

### `synthesizer(state, config)`
- Creates polished user response without tool bindings
- Uses:
  - `MOVIE_AGENT_SYSTEM_PROMPT`
  - `history_summary`
  - `optimized_prompt`
  - flattened tool transcript
  - prior `quality_feedback` on retries
- Retry model behavior:
  - first pass: `OLLAMA_MODEL`
  - retry pass: `OLLAMA_SYNTH_FALLBACK_MODEL` or `OLLAMA_CODE_MODEL`

### `quality_eval(state, config)`
- Calls shared helper `evaluate_answer_quality(...)`
- Output: `quality_score`, `quality_feedback`
- Route rules:
  - accept if score >= `QUALITY_MIN_SCORE`
  - retry synth if under threshold and pass count < `MAX_SYNTHESIS_PASSES`

## Shared Helper Classes / Functions

### `ChatService` (`app/services/chat_service.py`)
- Primary orchestrator for sync and streaming chat
- Important methods:
  - `_try_semantic_cache(message)` -> vector lookup + optional verification
  - `process_message(...)` -> HTTP flow
  - `stream_message(..., regenerate=False)` -> WS streaming flow
  - `_agent_state_payload(...)` -> graph input packaging
  - `_make_langfuse_handler()` -> per-request callback handler
- Regenerate mode:
  - reuses latest user message from DB
  - skips cache by design
  - appends new assistant response only

### `evaluate_answer_quality(...)` (`app/services/agent/quality.py`)
- Shared quality gate for:
  - cache path
  - graph output
  - regeneration output
- Uses same model family and deterministic parsing into `(score, reason)`

### `MessageRepository` (`app/repositories/conversation_repo.py`)
- `get_recent_by_conversation(...)` for rolling context
- `get_latest_user_message(conversation_id)` for regenerate
- `add_message(...)`, `set_message_feedback(...)`, `get_liked_messages(...)`

### Trace helpers (`app/services/agent/trace_events.py`)
- `build_agent_run_config(...)` -> tags + metadata + callbacks
- `append_trace_from_astream_event(...)` -> compact UI timeline
- `try_get_observability_trace_id(...)` -> Langfuse trace id extraction

## API Surface

### Chat
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Sync message-response |
| `GET` | `/api/v1/chat/conversations` | List conversations |
| `GET` | `/api/v1/chat/{conversation_id}` | Conversation with messages |
| `DELETE` | `/api/v1/chat/{conversation_id}` | Delete conversation |
| `POST` | `/api/v1/chat/message/{message_id}/feedback` | Like/dislike assistant message |
| `WS` | `/api/v1/chat/ws` | Streaming chat + regenerate (`regenerate: true`) |

### Movies
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/movies/search?q=...` | Search movie titles |
| `GET` | `/api/v1/movies/{imdb_id}` | Fetch movie detail |

## Core Packages Used

From `requirements.txt`:
- `fastapi`, `uvicorn` -> API + runtime
- `langchain`, `langgraph`, `langchain-ollama`, `langchain-community` -> agent pipeline
- `langfuse` -> observability/tracing
- `sqlalchemy[asyncio]`, `aiomysql` -> persistence
- `redis` -> semantic cache storage/search
- `httpx` -> external API clients
- `pydantic-settings` -> environment-driven config
- `python-dotenv` -> local env loading

## Environment Configuration (Key Runtime Flags)

```bash
# Base model
OLLAMA_MODEL=llama3.1

# Retry model when quality fails
OLLAMA_SYNTH_FALLBACK_MODEL=
OLLAMA_CODE_MODEL=deepseek-coder

# Quality controls
QUALITY_MIN_SCORE=6
MAX_SYNTHESIS_PASSES=2

# Semantic cache verification
SEMANTIC_CACHE_VERIFY=true
```

## Langfuse Observability

Run local stack:

```bash
docker compose up -d
```

Recommended config:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3001
LANGFUSE_PROJECT_NAME=movie-agent
```

Important notes:
- this project initializes Langfuse client on startup and uses per-request callback handlers
- traces are flushed after each graph run
- if OTLP endpoint `/api/public/otel/v1/traces` returns `404`, you are likely pointing to Langfuse v2

## Quick Start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```
