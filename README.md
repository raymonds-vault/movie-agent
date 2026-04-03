# 🎬 Movie Agent

An AI-powered movie assistant built with **FastAPI** and **LangChain**, using **Ollama** (llama3) for local LLM inference. Chat about movies, get recommendations, search for films, and discover trending content.

## Architecture

```
┌───────────────────────────────────────────────────────┐
│                    FastAPI Application                  │
├───────────────────────────────────────────────────────┤
│  Controllers (Thin)     │  /api/v1/chat               │
│                         │  /api/v1/movies              │
│                         │  /health                     │
├─────────────────────────┼─────────────────────────────┤
│  Service Layer          │  ChatService                 │
│  (Business Logic)       │  MovieService                │
│                         │  └─ Agent (LangChain)        │
├─────────────────────────┼─────────────────────────────┤
│  Repository Layer       │  ConversationRepo            │
│  (Data Access)          │  MessageRepo                 │
│                         │  MovieRepo (cache)           │
├─────────────────────────┼─────────────────────────────┤
│  Infrastructure         │  SQLite (async)              │
│                         │  Ollama (llama3)             │
│                         │  TMDB API (httpx)            │
└───────────────────────────────────────────────────────┘
```

**Dependency flow:** `Controller → Service → Repository` (strictly unidirectional)

## Prerequisites

- **Python 3.11+**
- **Ollama** running locally with `llama3` model pulled
- **TMDB API key** (free at [themoviedb.org](https://www.themoviedb.org/settings/api)) — optional for chat-only mode

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your TMDB_API_KEY

# 4. Ensure Ollama is running with llama3
ollama pull llama3

# 5. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat` | Send a message to the movie agent |
| `GET` | `/api/v1/chat/conversations` | List all conversations |
| `GET` | `/api/v1/chat/{id}` | Get conversation with messages |
| `DELETE` | `/api/v1/chat/{id}` | Delete a conversation |

### Movies (Direct TMDB access)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/movies/search?q=...` | Search movies by title |
| `GET` | `/api/v1/movies/trending` | Get trending movies |
| `GET` | `/api/v1/movies/{tmdb_id}` | Get movie details |
| `GET` | `/api/v1/movies/{tmdb_id}/recommendations` | Get similar movies |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with dependency status |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc API docs |

## Example Usage

```bash
# Chat with the agent
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the best sci-fi movies of all time?"}'

# Continue a conversation
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me more about the first one", "conversation_id": "YOUR_CONV_ID"}'

# Search movies directly
curl "http://localhost:8000/api/v1/movies/search?q=inception"

# Get trending movies
curl "http://localhost:8000/api/v1/movies/trending"
```

## Project Structure

```
app/
├── core/           # Config, DB, dependencies, exceptions, logging
├── models/         # SQLAlchemy ORM models (Conversation, Message, CachedMovie)
├── schemas/        # Pydantic DTOs (request/response validation)
├── repositories/   # Data access layer (generic CRUD + specialized queries)
├── services/       # Business logic layer
│   └── agent/      # LangChain agent (tools, prompts, factory)
├── controllers/    # FastAPI routers (thin — delegate to services)
├── utils/          # TMDB HTTP client
└── main.py         # App factory & lifespan
```

## Langfuse observability (optional, local Docker)

Run [Langfuse](https://langfuse.com) locally with the official stack (see [Langfuse Docker Compose](https://langfuse.com/docs/deployment/local)):

```bash
docker compose up -d
```

Docker Compose loads this project’s `.env`. Because the API often sets `DATABASE_URL` to **MySQL**, the compose file uses **`LANGFUSE_DATABASE_URL`** (defaulting to the bundled Postgres service) so Langfuse does not inherit the wrong scheme.

This repo includes [`docker-compose.yml`](docker-compose.yml) (upstream Langfuse v3 stack). The web UI is published on **`LANGFUSE_WEB_PORT` (default `3001`)** so it does not collide with an older Langfuse v2 instance often left on **3000**. Host ports **6380** and **5433** are used for Redis and Postgres so they do not clash with a typical local Redis on **6379** or Postgres on **5432**. Wait until the web UI is ready, then open **http://localhost:3001**, sign up, and use a project named **`movie-agent`** (or rename yours to match). Copy that project’s **public** and **secret** API keys.

Set in the API `.env` (never commit secrets). **`LANGFUSE_ENABLED` defaults to `true`**: once both keys are set, tracing turns on without an extra flag. Use `LANGFUSE_ENABLED=false` only if you want to keep keys in the file but disable export.

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3001
LANGFUSE_PROJECT_NAME=movie-agent
```

`LANGFUSE_HOST` must match your Langfuse base URL (with this compose file: `http://localhost:3001`); the app also sets `LANGFUSE_BASE_URL` for Langfuse SDK v4. Keys are scoped to the project you created in the UI. **Restart the API** after changing `.env` (settings are cached). LangGraph runs pass a per-request [`CallbackHandler`](https://langfuse.com/docs/integrations/langchain/tracing) and flush the client after each run so traces show up promptly. Runs include tags/metadata (`movie-agent`, `sync` or `stream`, `conversation_id`, `langfuse_project`).

If traces are still empty: confirm `docker compose ps` shows Langfuse healthy, open the UI on **`LANGFUSE_WEB_PORT`** (default **3001**), and ensure nothing sets `OTEL_SDK_DISABLED=true` in the API environment (that disables Langfuse export). On API startup, a probe logs an error if `LANGFUSE_HOST` points at a **v2** server (OTLP path returns **404**).

**“Setup Tracing” stays pending / dashboard empty:** the Python SDK sends traces over **OpenTelemetry** to `http://<LANGFUSE_HOST>/api/public/otel/v1/traces`. **Langfuse server v2 does not expose that route** (you will see `404` and logs like `Failed to export span batch code: 404`). Run the **v3** stack from this repo’s [`docker-compose.yml`](docker-compose.yml) (`langfuse/langfuse:3` and `langfuse/langfuse-worker:3`), then `docker compose pull && docker compose up -d`. Quick check (use your UI port): `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/api/public/otel/v1/traces` — **404** means the server is too old; on v3 you should get **405** (method not allowed for GET) or similar, not 404. Use API keys from the **v3** project (not an old v2 instance on port 3000).

This app uses **Ollama**; you do not need `OPENAI_API_KEY`.

The React **Trace** drawer shows the `astream_events` timeline; optional `observability_trace_id` links to Langfuse. For the drawer link, set `VITE_LANGFUSE_HOST` in `frontend/.env` (see `frontend/.env.example`).

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```
