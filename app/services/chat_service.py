"""Chat service with data-layer-first run persistence + projections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncGenerator
from typing import Any

import app.core.redis as redis_core
from langchain_ollama import OllamaEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AgentException, NotFoundException
from app.core.logging import get_logger
from app.repositories.agent_run_repo import (
    AgentRunRepository,
    CacheAuditRepository,
    ConversationSummaryRepository,
)
from app.repositories.conversation_repo import ConversationRepository, MessageRepository
from app.repositories.redis_repo import RedisMovieRepository, RedisProjectionRepository
from app.schemas.chat import ChatResponse, ConversationDetail, ConversationSummary, MessageSchema
from app.services.agent.agent import create_movie_agent
from app.services.agent.cache_verification import verify_semantic_cache_answer
from app.services.agent.langfuse_flush import flush_langfuse
from app.services.agent.quality import evaluate_answer_quality, should_run_llm_quality_eval
from app.services.agent.observability import log_agent_checkpoint, record_graph_completion
from app.services.agent.trace_events import (
    append_trace_from_astream_event,
    build_agent_run_config,
    try_get_observability_trace_id,
)
from app.services.projection_service import ProjectionService

logger = get_logger(__name__)

HISTORY_CONTEXT_MESSAGE_LIMIT = 10


def _astream_langgraph_node(event: dict) -> str | None:
    return (event.get("metadata") or {}).get("langgraph_node")


class ChatService:
    """
    Handles all chat business logic:
    - Conversation lifecycle (create, continue, delete)
    - Agent invocation with custom Graph Context loops
    - Message persistence
    """

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._conversation_repo = ConversationRepository(session)
        self._message_repo = MessageRepository(session)
        self._run_repo = AgentRunRepository(session)
        self._cache_audit_repo = CacheAuditRepository(session)
        self._summary_repo = ConversationSummaryRepository(session)
        self._agent = create_movie_agent(settings)
        self._embeddings = OllamaEmbeddings(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_EMBEDDING_MODEL,
        )
        self._redis_repo = (
            RedisMovieRepository(redis_core.redis_client) if redis_core.redis_client else None
        )
        proj_repo = (
            RedisProjectionRepository(redis_core.redis_client)
            if redis_core.redis_client
            else None
        )
        self._projection_service = ProjectionService(proj_repo)
        self.SIMILARITY_THRESHOLD = 0.2

    def _primary_llm_label(self) -> str:
        if self._settings.openai_configured:
            tiers = self._settings.openai_chat_tiers
            return tiers[0] if tiers else "gpt-4o-mini"
        return self._settings.OLLAMA_MODEL

    @staticmethod
    def _context_hash(user_query: str, history_summary: str | None, user_scope: str) -> str:
        raw = f"{user_scope}::{history_summary or ''}::{user_query}".encode()
        return hashlib.sha256(raw).hexdigest()

    def _agent_state_payload(
        self,
        conversation,
        message: str,
        history_records,
        feedback_context: str,
        history_summary: str | None = None,
    ) -> dict:
        return {
            "conversation_id": conversation.id,
            "user_query": message,
            "raw_history": [{"role": m.role, "content": m.content} for m in history_records],
            "feedback_context": feedback_context,
            "history_summary": history_summary,
        }

    def _make_langfuse_handler(self):
        """One CallbackHandler per graph run (do not share across concurrent streams)."""
        if not self._settings.langfuse_configured:
            return None
        from langfuse.langchain import CallbackHandler

        pk = (self._settings.LANGFUSE_PUBLIC_KEY or "").strip()
        return CallbackHandler(public_key=pk) if pk else CallbackHandler()

    @staticmethod
    def _redis_flat_fields_to_doc(fields: list) -> dict[str, str]:
        doc: dict[str, str] = {}
        for i in range(0, len(fields), 2):
            key_raw, val_raw = fields[i], fields[i + 1]
            key = key_raw.decode() if isinstance(key_raw, bytes) else key_raw
            val = val_raw.decode() if isinstance(val_raw, bytes) else val_raw
            doc[key] = val
        return doc

    async def _try_semantic_cache(
        self,
        message: str,
        *,
        conversation_id: str,
        user_scope: str,
        context_hash: str,
    ) -> tuple[list[float] | None, str | None, dict[str, Any]]:
        """
        Vector lookup in Redis; optionally LLM-verify the cached answer.
        Returns (query_embedding, cached_reply) only when the hit is accepted;
        otherwise (embedding_or_none, None) so the agent path can run without duplicate DB rows.
        """
        if not self._redis_repo:
            return None, None, {"decision": "miss", "reason": "redis_unavailable"}

        query_vector: list[float] | None = None
        try:
            query_vector = await self._embeddings.aembed_query(message)
            res = await self._redis_repo.search_similar(message, query_vector, k=1)
            if len(res) <= 2:
                await self._cache_audit_repo.log_decision(
                    query=message,
                    decision="miss",
                    reason="no_result",
                    conversation_id=conversation_id,
                    user_scope=user_scope,
                    context_hash=context_hash,
                )
                return query_vector, None, {"decision": "miss", "reason": "no_result"}

            doc = self._redis_flat_fields_to_doc(res[2])
            score = float(doc.get("score", 1.0))
            cached_response = doc.get("response", "")
            hit_user_scope = doc.get("user_scope", "")
            hit_ctx = doc.get("context_hash", "")

            if score >= self.SIMILARITY_THRESHOLD or not cached_response:
                await self._cache_audit_repo.log_decision(
                    query=message,
                    decision="miss",
                    reason="score_or_empty",
                    similarity_score=score,
                    conversation_id=conversation_id,
                    user_scope=user_scope,
                    context_hash=context_hash,
                )
                return query_vector, None, {"decision": "miss", "reason": "score_or_empty", "score": score}

            if hit_user_scope and hit_user_scope != user_scope:
                await self._cache_audit_repo.log_decision(
                    query=message,
                    decision="rejected",
                    reason="user_scope_mismatch",
                    similarity_score=score,
                    conversation_id=conversation_id,
                    user_scope=user_scope,
                    context_hash=context_hash,
                )
                return query_vector, None, {"decision": "rejected", "reason": "user_scope_mismatch", "score": score}

            if hit_ctx and hit_ctx != context_hash:
                await self._cache_audit_repo.log_decision(
                    query=message,
                    decision="rejected",
                    reason="context_hash_mismatch",
                    similarity_score=score,
                    conversation_id=conversation_id,
                    user_scope=user_scope,
                    context_hash=context_hash,
                )
                return query_vector, None, {"decision": "rejected", "reason": "context_hash_mismatch", "score": score}

            logger.info(
                "Semantic cache candidate (score=%s) for: %r",
                score,
                message[:200],
            )

            if self._settings.SEMANTIC_CACHE_VERIFY:
                verified = await verify_semantic_cache_answer(
                    self._settings, message, cached_response
                )
                if not verified:
                    logger.info(
                        "Semantic cache rejected by verifier; continuing with agent pipeline"
                    )
                    await self._cache_audit_repo.log_decision(
                        query=message,
                        decision="rejected",
                        reason="llm_verifier",
                        similarity_score=score,
                        conversation_id=conversation_id,
                        user_scope=user_scope,
                        context_hash=context_hash,
                    )
                    return query_vector, None, {"decision": "rejected", "reason": "llm_verifier", "score": score}
                logger.info("Semantic cache hit verified")
            else:
                logger.info(
                    "Semantic cache hit (verification disabled, score=%s)",
                    score,
                )

            await self._cache_audit_repo.log_decision(
                query=message,
                decision="hit_candidate",
                reason="vector_match",
                similarity_score=score,
                conversation_id=conversation_id,
                user_scope=user_scope,
                context_hash=context_hash,
            )
            return query_vector, cached_response, {"decision": "hit_candidate", "score": score}
        except Exception as e:
            logger.error(f"Semantic cache error: {e}")
            await self._cache_audit_repo.log_decision(
                query=message,
                decision="error",
                reason=str(e),
                conversation_id=conversation_id,
                user_scope=user_scope,
                context_hash=context_hash,
            )
            return query_vector, None, {"decision": "error", "reason": str(e)}

    async def _latest_summary_text(self, conversation_id: str) -> str | None:
        proj = await self._projection_service.get_conversation_projection(conversation_id)
        if proj and proj.get("summary_text"):
            return proj["summary_text"]
        latest = await self._summary_repo.get_latest(conversation_id)
        if latest:
            return latest.summary_text
        return None

    async def _capture_graph_event_for_run(
        self,
        *,
        run_id: str,
        event: dict[str, Any],
        tool_calls_made: list[str],
    ) -> tuple[str | None, str | None, int | None, str | None]:
        kind = event.get("event", "")
        node = _astream_langgraph_node(event) or event.get("name", "unknown")
        detail = None
        history_summary = None
        optimized_prompt = None
        quality_score = None
        quality_feedback = None
        if kind in {"on_chain_end", "on_chain_start", "on_tool_start", "on_tool_end"}:
            data = event.get("data") or {}
            detail = json.dumps(data, default=str)[:1500] if data else None
            await self._run_repo.add_step(
                run_id=run_id,
                node_name=str(node),
                event=kind,
                detail=detail,
            )
            if kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_calls_made.append(tool_name)
                inp = (event.get("data") or {}).get("input")
                await self._run_repo.add_tool_call(
                    run_id=run_id,
                    tool_name=tool_name,
                    tool_input=str(inp)[:1000] if inp is not None else None,
                    success=True,
                )
            if kind == "on_chain_end":
                out = data.get("output")
                if isinstance(out, dict):
                    if "history_summary" in out:
                        history_summary = str(out.get("history_summary") or "")
                    if "optimized_prompt" in out:
                        optimized_prompt = str(out.get("optimized_prompt") or "")
                    if "quality_score" in out:
                        try:
                            quality_score = int(out.get("quality_score"))
                        except Exception:
                            pass
                    if "quality_feedback" in out:
                        quality_feedback = str(out.get("quality_feedback") or "")
        return history_summary, optimized_prompt, quality_score, quality_feedback

    @staticmethod
    def _observability_from_last_chain_output(event: dict[str, Any]) -> dict[str, Any]:
        """Extract checkpoint fields from a graph node's chain end output."""
        if event.get("event") != "on_chain_end":
            return {}
        out = (event.get("data") or {}).get("output")
        if not isinstance(out, dict):
            return {}
        obs: dict[str, Any] = {}
        if "retrieval_score" in out:
            obs["retrieval_score"] = out.get("retrieval_score")
        if "tool_used" in out:
            obs["tool_used"] = out.get("tool_used")
        if "eval_score" in out and out.get("eval_score") is not None:
            try:
                obs["eval_score"] = int(out.get("eval_score"))
            except Exception:
                obs["eval_score"] = out.get("eval_score")
        if "retry_count" in out:
            try:
                obs["retry_count"] = int(out.get("retry_count") or 0)
            except Exception:
                obs["retry_count"] = 0
        if "quality_score" in out:
            try:
                obs["eval_score"] = int(out.get("quality_score"))
            except Exception:
                pass
        return obs

    async def process_message(
        self,
        message: str,
        conversation_id: str | None = None,
        *,
        user_id: str | None,
    ) -> ChatResponse:
        if conversation_id:
            conversation = await self._conversation_repo.get_with_messages(
                conversation_id, user_id=user_id
            )
            if not conversation:
                raise NotFoundException("Conversation", conversation_id)
        else:
            conversation = await self._conversation_repo.create(
                user_id=user_id,
                title=message[:50] + ("..." if len(message) > 50 else ""),
            )
            logger.info(f"New conversation created: {conversation.id}")

        existing_summary = await self._latest_summary_text(conversation.id)
        user_scope = f"conversation:{conversation.id}"
        context_hash = self._context_hash(message, existing_summary, user_scope)

        query_vector, cached_response, _cache_meta = await self._try_semantic_cache(
            message,
            conversation_id=conversation.id,
            user_scope=user_scope,
            context_hash=context_hash,
        )

        if cached_response is not None:
            cache_run = await self._run_repo.create_run(
                conversation_id=conversation.id,
                user_query=message,
                source="cache",
                path="sync",
                history_summary=existing_summary,
            )
            needs_eval, reason = should_run_llm_quality_eval(
                self._settings,
                user_query=message,
                draft_response=cached_response,
                tool_calls_made=["cache"],
            )
            if needs_eval:
                q_score, _ = await evaluate_answer_quality(
                    self._settings,
                    user_query=message,
                    draft_response=cached_response,
                    source="cache",
                )
            else:
                q_score = 10
            await self._run_repo.add_quality_evaluation(
                run_id=cache_run.id,
                source="cache",
                score=q_score,
                reason=reason,
                model_name=self._primary_llm_label(),
            )
            if q_score >= self._settings.QUALITY_MIN_SCORE:
                cache_tool_calls = (
                    '["cache","cache_verified"]'
                    if self._settings.SEMANTIC_CACHE_VERIFY
                    else '["cache"]'
                )
                tool_calls_made = (
                    ["cache", "cache_verified"]
                    if self._settings.SEMANTIC_CACHE_VERIFY
                    else ["cache"]
                )
                await self._message_repo.add_message(
                    conversation_id=conversation.id, role="user", content=message
                )
                await self._message_repo.add_message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=cached_response,
                    tool_calls=cache_tool_calls,
                )
                await self._run_repo.finalize_run(
                    cache_run.id,
                    status="completed",
                    final_response=cached_response,
                    quality_score=q_score,
                    history_summary=existing_summary,
                )
                await self._projection_service.update_run_projection(
                    cache_run.id,
                    conversation_id=conversation.id,
                    status="completed",
                    quality_score=q_score,
                    tools=["cache"],
                )
                log_agent_checkpoint(
                    conversation_id=str(conversation.id),
                    run_id=str(cache_run.id),
                    retrieval_score=None,
                    tool_used="cache",
                    eval_score=q_score,
                    retry_count=0,
                )
                return ChatResponse(
                    conversation_id=conversation.id,
                    reply=cached_response,
                    tool_calls_made=tool_calls_made,
                )
            await self._run_repo.finalize_run(
                cache_run.id,
                status="rejected",
                quality_score=q_score,
                quality_feedback="cache_quality_rejected",
                history_summary=existing_summary,
            )
            logger.info(
                "Semantic cache hit failed quality (%s); running full pipeline",
                q_score,
            )

        # 3. Save user message
        await self._message_repo.add_message(
            conversation_id=conversation.id,
            role="user",
            content=message,
        )

        history_records = await self._message_repo.get_conversation_context(
            conversation.id, token_limit=1200
        )
        if user_id is not None:
            liked_messages = await self._message_repo.get_liked_messages_for_user(
                user_id, limit=5
            )
        else:
            liked_messages = []
        feedback_context = " | ".join([m.content for m in liked_messages]) if liked_messages else "None"

        run = await self._run_repo.create_run(
            conversation_id=conversation.id,
            user_query=message,
            source="graph",
            path="sync",
            history_summary=existing_summary,
        )
        trace_steps: list[dict] = []
        reply_text = ""
        tool_calls_made: list[str] = []
        lf_handler = self._make_langfuse_handler()
        callbacks = [lf_handler] if lf_handler else None
        observability_trace_id: str | None = None
        last_quality_score: int | None = None
        last_quality_feedback: str | None = None
        latest_history_summary: str | None = existing_summary
        latest_optimized_prompt: str | None = None
        last_obs: dict[str, Any] = {}
        try:
            agent_input = self._agent_state_payload(
                conversation,
                message,
                history_records,
                feedback_context,
                history_summary=existing_summary,
            )
            run_config = build_agent_run_config(
                self._settings,
                conversation_id=str(conversation.id),
                path="sync",
                callbacks=callbacks,
            )

            async for event in self._agent.astream_events(
                agent_input,
                config=run_config,
                version="v2",
            ):
                append_trace_from_astream_event(event, trace_steps)
                last_obs.update(self._observability_from_last_chain_output(event))
                kind = event.get("event")
                hs, op, qs, qf = await self._capture_graph_event_for_run(
                    run_id=run.id,
                    event=event,
                    tool_calls_made=tool_calls_made,
                )
                if hs is not None:
                    latest_history_summary = hs
                if op is not None:
                    latest_optimized_prompt = op
                if qs is not None:
                    last_quality_score = qs
                if qf is not None:
                    last_quality_feedback = qf
                if kind == "on_chain_start":
                    node = _astream_langgraph_node(event)
                    if node == "synthesizer":
                        reply_text = ""
                elif kind == "on_chat_model_stream":
                    if _astream_langgraph_node(event) != "synthesizer":
                        continue
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        reply_text += str(chunk.content)
                elif kind == "on_chat_model_end":
                    if _astream_langgraph_node(event) != "synthesizer":
                        continue
                    out = event.get("data", {}).get("output")
                    if out is not None and hasattr(out, "content") and out.content:
                        if not reply_text:
                            reply_text = str(out.content)

            if lf_handler is not None:
                flush_langfuse()

            observability_trace_id = try_get_observability_trace_id(lf_handler)

            if not reply_text:
                reply_text = "I'm sorry, I couldn't generate a response. Please try again."

            escalated = int(last_obs.get("retry_count") or 0) > 0
            record_graph_completion(escalated=escalated)
            log_agent_checkpoint(
                conversation_id=str(conversation.id),
                run_id=str(run.id),
                retrieval_score=last_obs.get("retrieval_score"),
                tool_used=last_obs.get("tool_used"),
                eval_score=last_obs.get("eval_score") if last_obs.get("eval_score") is not None else last_quality_score,
                retry_count=last_obs.get("retry_count"),
            )

        except Exception as e:
            logger.error(f"Agent invocation failed: {e}", exc_info=True)
            raise AgentException(f"Failed to process your message: {str(e)}")

        # Save assistant response
        await self._message_repo.add_message(
            conversation_id=conversation.id,
            role="assistant",
            content=reply_text,
            tool_calls=json.dumps(tool_calls_made) if tool_calls_made else None,
        )

        # Store in Redis semantic cache
        if self._redis_repo and query_vector and reply_text:
            await self._redis_repo.store_query(
                message,
                reply_text,
                query_vector,
                user_scope=user_scope,
                context_hash=context_hash,
                confidence=float(last_quality_score or 0),
            )

        await self._run_repo.add_quality_evaluation(
            run_id=run.id,
            source="graph",
            score=last_quality_score or 0,
            reason=last_quality_feedback,
            model_name=self._primary_llm_label(),
        )
        await self._run_repo.finalize_run(
            run.id,
            status="completed",
            final_response=reply_text,
            quality_score=last_quality_score,
            quality_feedback=last_quality_feedback,
            optimized_prompt=latest_optimized_prompt,
            history_summary=latest_history_summary,
            observability_trace_id=observability_trace_id,
        )
        if latest_history_summary:
            await self._summary_repo.upsert_next(
                conversation_id=conversation.id,
                summary_text=latest_history_summary,
            )
        await self._projection_service.update_conversation_projection(
            conversation.id,
            summary_text=latest_history_summary,
            latest_run_id=run.id,
            latest_quality_score=last_quality_score,
        )
        await self._projection_service.update_run_projection(
            run.id,
            conversation_id=conversation.id,
            status="completed",
            quality_score=last_quality_score,
            tools=tool_calls_made,
        )

        return ChatResponse(
            conversation_id=conversation.id,
            reply=reply_text,
            tool_calls_made=tool_calls_made,
            agent_trace=trace_steps,
            observability_trace_id=observability_trace_id,
        )

    async def stream_message(
        self,
        message: str | None = None,
        conversation_id: str | None = None,
        *,
        user_id: str | None,
        regenerate: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Stream assistant reply. ``regenerate=True`` re-runs the last user message in the conversation
        (skips cache; does not insert a duplicate user row).
        """
        skip_user_insert = False
        query_vector: list[float] | None = None
        parent_run_id: str | None = None

        if regenerate:
            if not conversation_id:
                yield json.dumps(
                    {"type": "error", "content": "conversation_id is required to regenerate"}
                )
                return
            conversation = await self._conversation_repo.get_with_messages(
                conversation_id, user_id=user_id
            )
            if not conversation:
                yield json.dumps({"type": "error", "content": "Conversation not found"})
                return
            last_user = await self._message_repo.get_latest_user_message(conversation_id)
            if not last_user:
                yield json.dumps(
                    {"type": "error", "content": "No user message to regenerate from"}
                )
                return
            message = last_user.content
            skip_user_insert = True
            last_run = await self._run_repo.get_latest_by_conversation(conversation_id)
            parent_run_id = last_run.id if last_run else None
        else:
            if not (message or "").strip():
                yield json.dumps({"type": "error", "content": "message is required"})
                return
            message = message.strip()
            if conversation_id:
                conversation = await self._conversation_repo.get_with_messages(
                    conversation_id, user_id=user_id
                )
                if not conversation:
                    yield json.dumps({"type": "error", "content": "Conversation not found"})
                    return
            else:
                conversation = await self._conversation_repo.create(
                    user_id=user_id,
                    title=message[:50] + ("..." if len(message) > 50 else ""),
                )

        yield json.dumps({"type": "info", "conversation_id": conversation.id})

        cached_response: str | None = None
        existing_summary = await self._latest_summary_text(conversation.id)
        user_scope = f"conversation:{conversation.id}"
        context_hash = self._context_hash(message, existing_summary, user_scope)
        if not regenerate:
            query_vector, cached_response, _cache_meta = await self._try_semantic_cache(
                message,
                conversation_id=conversation.id,
                user_scope=user_scope,
                context_hash=context_hash,
            )
            if cached_response is not None:
                cache_run = await self._run_repo.create_run(
                    conversation_id=conversation.id,
                    user_query=message,
                    source="cache",
                    path="stream",
                    history_summary=existing_summary,
                )
                needs_eval, reason = should_run_llm_quality_eval(
                    self._settings,
                    user_query=message,
                    draft_response=cached_response,
                    tool_calls_made=["cache"],
                )
                if needs_eval:
                    q_score, _ = await evaluate_answer_quality(
                        self._settings,
                        user_query=message,
                        draft_response=cached_response,
                        source="cache",
                    )
                else:
                    q_score = 10
                await self._run_repo.add_quality_evaluation(
                    run_id=cache_run.id,
                    source="cache",
                    score=q_score,
                    reason=reason,
                    model_name=self._primary_llm_label(),
                )
                if q_score >= self._settings.QUALITY_MIN_SCORE:
                    cache_tool_calls = (
                        '["cache","cache_verified"]'
                        if self._settings.SEMANTIC_CACHE_VERIFY
                        else '["cache"]'
                    )
                    await self._message_repo.add_message(
                        conversation_id=conversation.id, role="user", content=message
                    )
                    await self._message_repo.add_message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=cached_response,
                        tool_calls=cache_tool_calls,
                    )
                    await self._run_repo.finalize_run(
                        cache_run.id,
                        status="completed",
                        final_response=cached_response,
                        quality_score=q_score,
                        history_summary=existing_summary,
                    )
                    await self._projection_service.update_run_projection(
                        cache_run.id,
                        conversation_id=conversation.id,
                        status="completed",
                        quality_score=q_score,
                        tools=["cache"],
                    )
                    log_agent_checkpoint(
                        conversation_id=str(conversation.id),
                        run_id=str(cache_run.id),
                        retrieval_score=None,
                        tool_used="cache",
                        eval_score=q_score,
                        retry_count=0,
                    )

                    yield json.dumps({"type": "status", "content": "Cache hit…"})
                    yield json.dumps({"type": "token", "content": cached_response})
                    yield json.dumps({"type": "status", "content": ""})
                    yield json.dumps({"type": "done"})
                    return
                logger.info(
                    "Stream: cache failed quality (%s); full pipeline",
                    q_score,
                )
                await self._run_repo.finalize_run(
                    cache_run.id,
                    status="rejected",
                    quality_score=q_score,
                    quality_feedback="cache_quality_rejected",
                )

        if not skip_user_insert:
            await self._message_repo.add_message(
                conversation_id=conversation.id,
                role="user",
                content=message,
            )

        history_records = await self._message_repo.get_conversation_context(
            conversation.id, token_limit=1200
        )
        if user_id is not None:
            liked_messages = await self._message_repo.get_liked_messages_for_user(
                user_id, limit=5
            )
        else:
            liked_messages = []
        feedback_context = (
            " | ".join([m.content for m in liked_messages]) if liked_messages else "None"
        )

        reply_text = ""
        tool_calls_made: list[str] = []
        trace_steps: list[dict] = []
        lf_handler = self._make_langfuse_handler()
        callbacks = [lf_handler] if lf_handler else None
        run = await self._run_repo.create_run(
            conversation_id=conversation.id,
            user_query=message,
            source="regenerate" if regenerate else "graph",
            path="stream",
            parent_run_id=parent_run_id,
            history_summary=existing_summary,
        )
        last_quality_score: int | None = None
        last_quality_feedback: str | None = None
        latest_history_summary: str | None = existing_summary
        latest_optimized_prompt: str | None = None
        last_obs: dict[str, Any] = {}

        try:
            yield json.dumps({"type": "status", "content": "Preparing context…"})

            agent_input = self._agent_state_payload(
                conversation,
                message,
                history_records,
                feedback_context,
                history_summary=existing_summary,
            )
            run_config = build_agent_run_config(
                self._settings,
                conversation_id=str(conversation.id),
                path="stream",
                callbacks=callbacks,
            )

            async for event in self._agent.astream_events(
                agent_input,
                config=run_config,
                version="v2",
            ):
                append_trace_from_astream_event(event, trace_steps)
                last_obs.update(self._observability_from_last_chain_output(event))
                kind = event["event"]
                hs, op, qs, qf = await self._capture_graph_event_for_run(
                    run_id=run.id,
                    event=event,
                    tool_calls=tool_calls_made,
                )
                if hs is not None:
                    latest_history_summary = hs
                if op is not None:
                    latest_optimized_prompt = op
                if qs is not None:
                    last_quality_score = qs
                if qf is not None:
                    last_quality_feedback = qf

                if kind == "on_chain_start":
                    meta = event.get("metadata") or {}
                    node_name = meta.get("langgraph_node") or event.get("name", "")
                    if node_name == "synthesizer":
                        reply_text = ""
                    if node_name == "pinecone_context":
                        yield json.dumps({"type": "status", "content": "Retrieving movie context…"})
                    elif node_name == "context_builder":
                        yield json.dumps({"type": "status", "content": "Preparing context…"})
                    elif node_name == "tools_decision":
                        yield json.dumps({"type": "status", "content": "Deciding tool call…"})
                    elif node_name == "tool_executor":
                        yield json.dumps({"type": "status", "content": "Running tool…"})
                    elif node_name == "synthesizer":
                        yield json.dumps({"type": "status", "content": "Writing reply…"})
                    elif node_name == "eval_gate":
                        yield json.dumps({"type": "status", "content": "Rule quality check…"})
                    elif node_name == "quality_eval":
                        yield json.dumps({"type": "status", "content": "Checking quality…"})

                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    yield json.dumps({"type": "status", "content": f"Tool: {tool_name}…"})

                elif kind == "on_chat_model_stream":
                    if _astream_langgraph_node(event) != "synthesizer":
                        continue
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        content_str = str(chunk.content)
                        reply_text += content_str
                        yield json.dumps({"type": "token", "content": content_str})

            if lf_handler is not None:
                flush_langfuse()

            escalated = int(last_obs.get("retry_count") or 0) > 0
            record_graph_completion(escalated=escalated)
            log_agent_checkpoint(
                conversation_id=str(conversation.id),
                run_id=str(run.id),
                retrieval_score=last_obs.get("retrieval_score"),
                tool_used=last_obs.get("tool_used"),
                eval_score=last_obs.get("eval_score")
                if last_obs.get("eval_score") is not None
                else last_quality_score,
                retry_count=last_obs.get("retry_count"),
            )

            yield json.dumps({"type": "status", "content": ""})

            observability_trace_id = try_get_observability_trace_id(lf_handler)
            yield json.dumps(
                {
                    "type": "agent_trace",
                    "steps": trace_steps,
                    "observability_trace_id": observability_trace_id,
                }
            )

        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            await self._run_repo.finalize_run(
                run.id,
                status="failed",
                quality_feedback=str(e),
                optimized_prompt=latest_optimized_prompt,
                history_summary=latest_history_summary,
            )
            yield json.dumps({"type": "error", "content": "Error generating response."})

        if reply_text:
            saved_msg = await self._message_repo.add_message(
                conversation_id=conversation.id,
                role="assistant",
                content=reply_text,
                tool_calls=json.dumps(tool_calls_made) if tool_calls_made else None,
            )
            yield json.dumps({"type": "message_id", "message_id": saved_msg.id})

            if self._redis_repo and query_vector is None:
                try:
                    query_vector = await self._embeddings.aembed_query(message)
                except Exception as e:
                    logger.warning("Redis embed for store failed: %s", e)
            if self._redis_repo and query_vector:
                await self._redis_repo.store_query(
                    message,
                    reply_text,
                    query_vector,
                    user_scope=user_scope,
                    context_hash=context_hash,
                    confidence=float(last_quality_score or 0),
                )

            await self._run_repo.add_quality_evaluation(
                run_id=run.id,
                source="regenerate" if regenerate else "graph",
                score=last_quality_score or 0,
                reason=last_quality_feedback,
                model_name=self._primary_llm_label(),
            )
            obs_tid = try_get_observability_trace_id(lf_handler)
            await self._run_repo.finalize_run(
                run.id,
                status="completed",
                final_response=reply_text,
                quality_score=last_quality_score,
                quality_feedback=last_quality_feedback,
                optimized_prompt=latest_optimized_prompt,
                history_summary=latest_history_summary,
                observability_trace_id=obs_tid,
            )
            if latest_history_summary:
                await self._summary_repo.upsert_next(
                    conversation_id=conversation.id,
                    summary_text=latest_history_summary,
                )
            await self._projection_service.update_conversation_projection(
                conversation.id,
                summary_text=latest_history_summary,
                latest_run_id=run.id,
                latest_quality_score=last_quality_score,
            )
            await self._projection_service.update_run_projection(
                run.id,
                conversation_id=conversation.id,
                status="completed",
                quality_score=last_quality_score,
                tools=tool_calls_made,
            )

        yield json.dumps({"type": "done"})

    async def get_conversation(self, conversation_id: str, *, user_id: str | None) -> ConversationDetail:
        conversation = await self._conversation_repo.get_with_messages(
            conversation_id, user_id=user_id
        )
        if not conversation:
            raise NotFoundException("Conversation", conversation_id)

        return ConversationDetail(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            messages=[
                MessageSchema.model_validate(m) for m in conversation.messages
            ],
        )

    async def list_conversations(
        self, user_id: str | None, offset: int = 0, limit: int = 20
    ) -> list[ConversationSummary]:
        conversations = await self._conversation_repo.list_conversations(
            user_id, offset=offset, limit=limit
        )
        return [
            ConversationSummary(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                message_count=len(c.messages),
            )
            for c in conversations
        ]

    async def delete_conversation(self, conversation_id: str, *, user_id: str | None) -> None:
        conversation = await self._conversation_repo.get_with_messages(
            conversation_id, user_id=user_id
        )
        if not conversation:
            raise NotFoundException("Conversation", conversation_id)
        await self._conversation_repo.delete(conversation)
        logger.info(f"Conversation deleted: {conversation_id}")

    async def submit_feedback(self, message_id: str, is_liked: bool, *, user_id: str):
        message = await self._message_repo.get_by_id(message_id)
        if not message:
            raise NotFoundException("Message", message_id)
        conv = await self._conversation_repo.get_by_id(message.conversation_id)
        if not conv or conv.user_id != user_id:
            raise NotFoundException("Message", message_id)
        updated = await self._message_repo.set_message_feedback(message_id, is_liked)
        if not updated:
            raise NotFoundException("Message", message_id)
        return updated

    async def get_tool_usage_stats(
        self, tool_name: str | None = None, *, user_id: str | None
    ) -> list[dict]:
        if user_id is None:
            return []
        return await self._run_repo.get_tool_usage_stats(
            tool_name=tool_name, user_id=user_id
        )

    async def get_run_failure_breakdown(self, *, user_id: str | None) -> list[dict]:
        if user_id is None:
            return []
        return await self._run_repo.get_run_failure_breakdown(user_id=user_id)

    async def get_cache_decision_stats(self, *, user_id: str | None) -> list[dict]:
        if user_id is None:
            return []
        return await self._cache_audit_repo.decision_stats(user_id=user_id)
