"""
Chat-related Pydantic schemas (request/response DTOs).
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message from the user."""

    message: str = Field(..., min_length=1, max_length=5000, description="User's message")
    conversation_id: str | None = Field(
        default=None, description="Existing conversation ID to continue; omit to start a new one"
    )

class FeedbackRequest(BaseModel):
    is_liked: bool = Field(..., description="True indicating thumbs up, False for thumbs down")


class MessageSchema(BaseModel):
    """Single message in a conversation."""

    id: str
    role: str
    content: str
    tool_calls: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    """Response from the agent."""

    conversation_id: str
    reply: str
    tool_calls_made: list[str] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    """Brief conversation overview for listing."""

    id: str
    title: str
    created_at: datetime
    message_count: int

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    """Full conversation with all messages."""

    id: str
    title: str
    created_at: datetime
    messages: list[MessageSchema]

    model_config = {"from_attributes": True}
