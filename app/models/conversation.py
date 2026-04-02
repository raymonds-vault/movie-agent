"""
Conversation and Message ORM models.
Stores chat history for multi-turn conversations.
"""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Conversation(Base, UUIDMixin, TimestampMixin):
    """A conversation session with the movie agent."""

    __tablename__ = "conversations"

    title: Mapped[str] = mapped_column(String(255), default="New Conversation")

    # Relationships
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"


class Message(Base, UUIDMixin, TimestampMixin):
    """A single message within a conversation."""

    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant" | "system"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string of tools used
    is_liked: Mapped[bool | None] = mapped_column(nullable=True)  # User feedback thumbs up/down

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role})>"
