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

    async def get_with_messages(
        self, conversation_id: str, *, user_id: str | None = None
    ) -> Conversation | None:
        """Fetch a conversation with all its messages eagerly loaded."""
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        else:
            stmt = stmt.where(Conversation.user_id.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_conversations(
        self, user_id: str | None, offset: int = 0, limit: int = 20
    ) -> list[Conversation]:
        """List conversations for a user, most recent first. ``user_id`` None returns []."""
        if user_id is None:
            return []
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


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
            .order_by(Message.created_at.asc(), Message.id.asc())
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
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def get_conversation_context(
        self, conversation_id: str, token_limit: int = 1200
    ) -> list[Message]:
        """
        Context-focused reader: pulls recent turns and trims by an approximate token budget.
        Uses ~4 chars/token approximation to stay lightweight without tokenizer dependency.
        """
        rows = await self.get_recent_by_conversation(conversation_id, limit=60)
        budget_chars = max(200, token_limit * 4)
        picked: list[Message] = []
        used = 0
        for m in reversed(rows):  # newest to oldest while filling budget
            size = len(m.content or "")
            if used + size > budget_chars and picked:
                break
            picked.append(m)
            used += size
        picked.reverse()
        return picked

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
            .where(Message.is_liked == True)  # noqa: E712
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_liked_messages_for_user(self, user_id: str, limit: int = 10) -> list[Message]:
        """Liked messages scoped to a user's conversations."""
        stmt = (
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Message.is_liked == True, Conversation.user_id == user_id)  # noqa: E712
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
