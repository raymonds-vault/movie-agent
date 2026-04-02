"""
Shared Pydantic schemas used across multiple features.
"""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error: str
    type: str


class PaginationParams(BaseModel):
    """Common pagination parameters."""

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    app_name: str
    ollama_status: str
    database_status: str
