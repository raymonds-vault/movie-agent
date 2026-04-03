"""
Conversation & Message repository.
Extends BaseRepository with conversation-specific queries.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, Message
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Data access for conversations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)

    async def get_with_messages(self, conversation_id: str) -> Conversation | None:
        """Fetch a conversation with all its messages eagerly loaded."""
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_conversations(
        self, offset: int = 0, limit: int = 20
    ) -> list[Conversation]:
        """List conversations ordered by most recent first."""
        return await self.get_all(
            offset=offset,
            limit=limit,
            order_by=Conversation.created_at.desc(),
        )


class MessageRepository(BaseRepository[Message]):
    """Data access for messages."""

    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def get_by_conversation(
        self, conversation_id: str, limit: int = 50
    ) -> list[Message]:
        """Fetch the oldest ``limit`` messages for a conversation, chronological order."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_by_conversation(
        self, conversation_id: str, limit: int = 10
    ) -> list[Message]:
        """Fetch the most recent ``limit`` messages, oldest-first (for prompts / summarization)."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: str | None = None,
    ) -> Message:
        """Add a new message to a conversation."""
        return await self.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
        )

    async def set_message_feedback(self, message_id: str, is_liked: bool) -> Message | None:
        """Update the is_liked status of a message."""
        message = await self.get_by_id(message_id)
        if message:
            message.is_liked = is_liked
            await self._session.commit()
        return message

    async def get_latest_user_message(self, conversation_id: str) -> Message | None:
        """Most recent user message in the conversation."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_liked_messages(self, limit: int = 10) -> list[Message]:
        """Fetch historically liked messages for optimized context generation."""
        stmt = (
            select(Message)
            .where(Message.is_liked == True)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
