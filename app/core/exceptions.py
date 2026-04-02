"""
Custom exception classes and FastAPI exception handlers.
Centralizes error handling so controllers stay thin.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# ── Exception Classes ────────────────────────────────


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str | int):
        super().__init__(
            message=f"{resource} with id '{identifier}' not found",
            status_code=404,
        )


class ExternalAPIException(AppException):
    """External API call failed."""

    def __init__(self, service: str, detail: str = ""):
        msg = f"External service '{service}' error"
        if detail:
            msg += f": {detail}"
        super().__init__(message=msg, status_code=502)


class AgentException(AppException):
    """LangChain agent invocation failed."""

    def __init__(self, detail: str = "Agent failed to process the request"):
        super().__init__(message=detail, status_code=500)


# ── Exception Handlers ──────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "type": type(exc).__name__},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "type": "UnhandledException"},
        )
