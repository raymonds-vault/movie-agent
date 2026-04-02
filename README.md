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

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```
