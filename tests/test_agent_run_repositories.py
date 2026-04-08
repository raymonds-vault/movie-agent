import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_run_repo import (
    AgentRunRepository,
    CacheAuditRepository,
    ConversationSummaryRepository,
)
from app.repositories.conversation_repo import ConversationRepository
from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_agent_run_lifecycle(db_session: AsyncSession, test_user):
    conv_repo = ConversationRepository(db_session)
    run_repo = AgentRunRepository(db_session)

    conversation = await conv_repo.create(user_id=test_user.id, title="Run lifecycle")
    run = await run_repo.create_run(
        conversation_id=conversation.id,
        user_query="hello",
        source="graph",
        path="sync",
    )
    assert run.status == "running"

    await run_repo.add_step(
        run_id=run.id,
        node_name="tools_phase",
        event="on_chain_start",
    )
    await run_repo.add_tool_call(
        run_id=run.id,
        tool_name="search_movies",
        tool_input="inception",
    )
    await run_repo.add_quality_evaluation(
        run_id=run.id,
        source="graph",
        score=8,
        reason="good",
    )
    finalized = await run_repo.finalize_run(
        run.id,
        status="completed",
        final_response="done",
        quality_score=8,
    )
    assert finalized is not None
    assert finalized.status == "completed"
    assert finalized.quality_score == 8


@pytest.mark.asyncio
async def test_cache_audit_and_summary(db_session: AsyncSession, test_user):
    conv_repo = ConversationRepository(db_session)
    cache_repo = CacheAuditRepository(db_session)
    summary_repo = ConversationSummaryRepository(db_session)

    conversation = await conv_repo.create(user_id=test_user.id, title="Summary test")
    await cache_repo.log_decision(
        query="recommend films",
        decision="hit",
        reason="vector",
        conversation_id=conversation.id,
        user_scope=f"conversation:{conversation.id}",
        context_hash="abc",
    )
    stats = await cache_repo.decision_stats()
    assert stats
    assert stats[0]["decision"] == "hit"

    s1 = await summary_repo.upsert_next(
        conversation_id=conversation.id,
        summary_text="first",
        token_count=10,
    )
    s2 = await summary_repo.upsert_next(
        conversation_id=conversation.id,
        summary_text="second",
        token_count=12,
    )
    assert s1.summary_version == 1
    assert s2.summary_version == 2
    latest = await summary_repo.get_latest(conversation.id)
    assert latest is not None
    assert latest.summary_text == "second"


def test_context_hash_changes_by_scope():
    a = ChatService._context_hash("q", "summary", "conversation:a")
    b = ChatService._context_hash("q", "summary", "conversation:b")
    assert a != b
