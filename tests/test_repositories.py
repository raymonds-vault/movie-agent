"""
Tests for conversation and message repositories.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_repo import ConversationRepository, MessageRepository


@pytest.mark.asyncio
async def test_create_conversation(db_session: AsyncSession):
    """Test creating a new conversation."""
    repo = ConversationRepository(db_session)
    conversation = await repo.create(title="Test Movie Chat")

    assert conversation.id is not None
    assert conversation.title == "Test Movie Chat"
    assert conversation.created_at is not None


@pytest.mark.asyncio
async def test_add_and_retrieve_messages(db_session: AsyncSession):
    """Test adding messages and retrieving them."""
    conv_repo = ConversationRepository(db_session)
    msg_repo = MessageRepository(db_session)

    # Create conversation
    conversation = await conv_repo.create(title="Chat about Inception")

    # Add messages
    msg1 = await msg_repo.add_message(
        conversation_id=conversation.id,
        role="user",
        content="Tell me about Inception",
    )
    msg2 = await msg_repo.add_message(
        conversation_id=conversation.id,
        role="assistant",
        content="Inception is a great movie!",
    )

    # Retrieve messages
    messages = await msg_repo.get_by_conversation(conversation.id)

    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[0].content == "Tell me about Inception"


@pytest.mark.asyncio
async def test_get_conversation_with_messages(db_session: AsyncSession):
    """Test eager loading of conversation with messages."""
    conv_repo = ConversationRepository(db_session)
    msg_repo = MessageRepository(db_session)

    conversation = await conv_repo.create(title="Movie Recs")
    conv_id = conversation.id

    await msg_repo.add_message(
        conversation_id=conv_id,
        role="user",
        content="Recommend action movies",
    )
    await db_session.commit()

    # Expunge the object from identity map so selectinload does a fresh DB query
    db_session.expunge(conversation)
    result = await conv_repo.get_with_messages(conv_id)

    assert result is not None
    assert result.title == "Movie Recs"
    assert len(result.messages) == 1


@pytest.mark.asyncio
async def test_delete_conversation_cascades(db_session: AsyncSession):
    """Test that deleting a conversation also deletes its messages."""
    conv_repo = ConversationRepository(db_session)
    msg_repo = MessageRepository(db_session)

    conversation = await conv_repo.create(title="To Delete")
    await msg_repo.add_message(
        conversation_id=conversation.id,
        role="user",
        content="This will be deleted",
    )
    await db_session.commit()

    await conv_repo.delete(conversation)
    await db_session.commit()

    # Verify conversation is gone
    result = await conv_repo.get_by_id(conversation.id)
    assert result is None

    # Verify messages are gone too
    messages = await msg_repo.get_by_conversation(conversation.id)
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_list_conversations_ordered(db_session: AsyncSession):
    """Test listing conversations in reverse chronological order."""
    conv_repo = ConversationRepository(db_session)

    await conv_repo.create(title="First")
    await conv_repo.create(title="Second")
    await conv_repo.create(title="Third")

    conversations = await conv_repo.list_conversations()

    assert len(conversations) == 3
    # Most recent first
    assert conversations[0].title == "Third"
