"""Auth-related API schemas."""

from pydantic import BaseModel, Field


class UserPublic(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None
    email_verified: bool = False


class WsAuthError(BaseModel):
    type: str = Field(default="error")
    content: str
