"""
FastAPI application factory.

Creates and configures the application with:
- Lifespan management (DB init/cleanup)
- CORS middleware
- Exception handlers
- Router registration
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.langfuse_setup import configure_langfuse
from app.core.database import init_db, shutdown_db
from app.core.redis import init_redis, close_redis
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: startup and shutdown events."""
    # ── Startup ──────────────────────────────────────
    setup_logging()

    from app.core.logging import get_logger
    logger = get_logger(__name__)

    settings = get_settings()
    configure_langfuse(settings)

    logger.info("🚀 Starting Movie Agent API...")
    await init_db()
    logger.info("✅ Database initialized")
    
    await init_redis()
    logger.info("✅ Redis initialized")

    logger.info(f"🤖 Ollama model: {settings.OLLAMA_MODEL} @ {settings.OLLAMA_BASE_URL}")
    logger.info(f"🎬 OMDb configured: {settings.omdb_configured}")

    react_proc = None
    if settings.AUTO_START_REACT_DEV:
        from app.core.react_dev import schedule_open_browser, start_react_dev_server

        react_proc = start_react_dev_server(
            logger,
            url=settings.REACT_DEV_URL,
        )
        if react_proc and settings.OPEN_REACT_BROWSER:
            schedule_open_browser(settings.REACT_DEV_URL, logger)

    yield

    # ── Shutdown ─────────────────────────────────────
    logger.info("👋 Shutting down Movie Agent API...")
    if settings.AUTO_START_REACT_DEV and react_proc is not None:
        from app.core.react_dev import stop_react_dev_server

        stop_react_dev_server(react_proc, logger)
    await close_redis()
    await shutdown_db()


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI app."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "🎬 An AI-powered movie agent built with FastAPI and LangChain. "
            "Chat about movies, get recommendations, search for films, "
            "and discover trending content — all powered by Ollama (llama3)."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware ────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ───────────────────────────
    register_exception_handlers(app)

    # ── Routers ──────────────────────────────────────
    from app.controllers.health_controller import router as health_router
    from app.controllers.chat_controller import router as chat_router
    from app.controllers.movie_controller import router as movie_router

    app.include_router(health_router)
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(movie_router, prefix="/api/v1")

    # ── Static Files ─────────────────────────────────
    import os
    if not os.path.exists("static"):
        os.makedirs("static")
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


# Module-level app instance for uvicorn
app = create_app()
