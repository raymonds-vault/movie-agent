"""
Tests for conversation and message repositories.
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_repo import ConversationRepository, MessageRepository


@pytest.mark.asyncio
async def test_create_conversation(db_session: AsyncSession, test_user):
    """Test creating a new conversation."""
    repo = ConversationRepository(db_session)
    conversation = await repo.create(user_id=test_user.id, title="Test Movie Chat")

    assert conversation.id is not None
    assert conversation.title == "Test Movie Chat"
    assert conversation.created_at is not None


@pytest.mark.asyncio
async def test_add_and_retrieve_messages(db_session: AsyncSession, test_user):
    """Test adding messages and retrieving them."""
    conv_repo = ConversationRepository(db_session)
    msg_repo = MessageRepository(db_session)

    conversation = await conv_repo.create(user_id=test_user.id, title="Chat about Inception")

    await msg_repo.add_message(
        conversation_id=conversation.id,
        role="user",
        content="Tell me about Inception",
    )
    await msg_repo.add_message(
        conversation_id=conversation.id,
        role="assistant",
        content="Inception is a great movie!",
    )

    messages = await msg_repo.get_by_conversation(conversation.id)

    assert len(messages) == 2
    by_role = {m.role: m for m in messages}
    assert by_role["user"].content == "Tell me about Inception"
    assert "great movie" in by_role["assistant"].content


@pytest.mark.asyncio
async def test_get_conversation_with_messages(db_session: AsyncSession, test_user):
    """Test eager loading of conversation with messages."""
    conv_repo = ConversationRepository(db_session)
    msg_repo = MessageRepository(db_session)

    conversation = await conv_repo.create(user_id=test_user.id, title="Movie Recs")
    conv_id = conversation.id

    await msg_repo.add_message(
        conversation_id=conv_id,
        role="user",
        content="Recommend action movies",
    )
    await db_session.commit()

    db_session.expunge(conversation)
    result = await conv_repo.get_with_messages(conv_id, user_id=test_user.id)

    assert result is not None
    assert result.title == "Movie Recs"
    assert len(result.messages) == 1


@pytest.mark.asyncio
async def test_delete_conversation_cascades(db_session: AsyncSession, test_user):
    """Test that deleting a conversation also deletes its messages."""
    conv_repo = ConversationRepository(db_session)
    msg_repo = MessageRepository(db_session)

    conversation = await conv_repo.create(user_id=test_user.id, title="To Delete")
    await msg_repo.add_message(
        conversation_id=conversation.id,
        role="user",
        content="This will be deleted",
    )
    await db_session.commit()

    await conv_repo.delete(conversation)
    await db_session.commit()

    result = await conv_repo.get_by_id(conversation.id)
    assert result is None

    messages = await msg_repo.get_by_conversation(conversation.id)
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_anonymous_conversation_create_and_fetch(db_session: AsyncSession):
    """Guest conversations have null user_id; fetch only when caller is anonymous."""
    conv_repo = ConversationRepository(db_session)
    conv = await conv_repo.create(user_id=None, title="Guest chat")
    await db_session.commit()
    got = await conv_repo.get_with_messages(conv.id, user_id=None)
    assert got is not None
    assert got.user_id is None
    assert await conv_repo.get_with_messages(conv.id, user_id="some-user-id") is None


@pytest.mark.asyncio
async def test_list_conversations_ordered(db_session: AsyncSession, test_user):
    """Test listing conversations in reverse chronological order."""
    conv_repo = ConversationRepository(db_session)

    await conv_repo.create(user_id=test_user.id, title="First")
    await asyncio.sleep(0.1)
    await conv_repo.create(user_id=test_user.id, title="Second")
    await asyncio.sleep(0.1)
    await conv_repo.create(user_id=test_user.id, title="Third")

    conversations = await conv_repo.list_conversations(test_user.id)

    assert len(conversations) == 3
    assert {c.title for c in conversations} == {"First", "Second", "Third"}
    assert conversations[0].created_at >= conversations[1].created_at >= conversations[2].created_at
