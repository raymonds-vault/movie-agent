"""
Chat service — orchestrates conversation flow and agent invocation.
This is the core business logic layer for the chat feature.
"""

import json

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AgentException, NotFoundException
from app.core.logging import get_logger
from app.repositories.conversation_repo import ConversationRepository, MessageRepository
from app.schemas.chat import ChatResponse, ConversationDetail, ConversationSummary, MessageSchema
from app.services.agent.agent import create_movie_agent
from app.services.agent.cache_verification import verify_semantic_cache_answer
from app.services.agent.quality import evaluate_answer_quality
from app.services.agent.langfuse_flush import flush_langfuse
from app.services.agent.trace_events import (
    append_trace_from_astream_event,
    build_agent_run_config,
    try_get_observability_trace_id,
)

import app.core.redis as redis_core
from app.repositories.redis_repo import RedisMovieRepository
from langchain_ollama import OllamaEmbeddings

logger = get_logger(__name__)

# Recent turns for context in the tools → LLM pipeline (latest messages in the thread).
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
        self._agent = create_movie_agent(settings)
        
        # Initialize semantic embeddings cache
        self._embeddings = OllamaEmbeddings(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_EMBEDDING_MODEL
        )
        self._redis_repo = RedisMovieRepository(redis_core.redis_client) if redis_core.redis_client else None
        self.SIMILARITY_THRESHOLD = 0.2

    def _agent_state_payload(
        self,
        conversation,
        message: str,
        history_records,
        feedback_context: str,
    ) -> dict:
        return {
            "conversation_id": conversation.id,
            "user_query": message,
            "raw_history": [{"role": m.role, "content": m.content} for m in history_records],
            "feedback_context": feedback_context,
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

    async def _try_semantic_cache(self, message: str) -> tuple[list[float] | None, str | None]:
        """
        Vector lookup in Redis; optionally LLM-verify the cached answer.
        Returns (query_embedding, cached_reply) only when the hit is accepted;
        otherwise (embedding_or_none, None) so the agent path can run without duplicate DB rows.
        """
        if not self._redis_repo:
            return None, None

        query_vector: list[float] | None = None
        try:
            query_vector = await self._embeddings.aembed_query(message)
            res = await self._redis_repo.search_similar(message, query_vector, k=1)
            if len(res) <= 2:
                return query_vector, None

            doc = self._redis_flat_fields_to_doc(res[2])
            score = float(doc.get("score", 1.0))
            cached_response = doc.get("response", "")

            if score >= self.SIMILARITY_THRESHOLD or not cached_response:
                return query_vector, None

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
                    return query_vector, None
                logger.info("Semantic cache hit verified")
            else:
                logger.info(
                    "Semantic cache hit (verification disabled, score=%s)",
                    score,
                )

            return query_vector, cached_response
        except Exception as e:
            logger.error(f"Semantic cache error: {e}")
            return query_vector, None

    async def process_message(
        self, message: str, conversation_id: str | None = None
    ) -> ChatResponse:
        # 1. Get or create conversation
        if conversation_id:
            conversation = await self._conversation_repo.get_with_messages(conversation_id)
            if not conversation:
                raise NotFoundException("Conversation", conversation_id)
        else:
            conversation = await self._conversation_repo.create(
                title=message[:50] + ("..." if len(message) > 50 else "")
            )
            logger.info(f"New conversation created: {conversation.id}")

        # 2. Semantic cache — same quality gate as the graph (below)
        query_vector, cached_response = await self._try_semantic_cache(message)

        if cached_response is not None:
            q_score, _ = await evaluate_answer_quality(
                self._settings,
                user_query=message,
                draft_response=cached_response,
                source="cache",
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
                return ChatResponse(
                    conversation_id=conversation.id,
                    reply=cached_response,
                    tool_calls_made=tool_calls_made,
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

        # 4. Prepare Context (most recent messages so follow-ups keep topic memory)
        history_records = await self._message_repo.get_recent_by_conversation(
            conversation.id, limit=HISTORY_CONTEXT_MESSAGE_LIMIT
        )
        liked_messages = await self._message_repo.get_liked_messages(limit=5)
        feedback_context = " | ".join([m.content for m in liked_messages]) if liked_messages else "None"

        # 5. Run the graph (astream_events: one pass + Langfuse callback + in-app trace)
        trace_steps: list[dict] = []
        reply_text = ""
        tool_calls_made: list[str] = []
        lf_handler = self._make_langfuse_handler()
        callbacks = [lf_handler] if lf_handler else None
        observability_trace_id: str | None = None
        try:
            agent_input = self._agent_state_payload(
                conversation, message, history_records, feedback_context
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
                kind = event.get("event")
                if kind == "on_chain_start":
                    node = _astream_langgraph_node(event)
                    if node == "synthesizer":
                        reply_text = ""
                elif kind == "on_tool_start":
                    tool_calls_made.append(event.get("name", "unknown"))
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
            await self._redis_repo.store_query(message, reply_text, query_vector)

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
        regenerate: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Stream assistant reply. ``regenerate=True`` re-runs the last user message in the conversation
        (skips cache; does not insert a duplicate user row).
        """
        skip_user_insert = False
        query_vector: list[float] | None = None

        if regenerate:
            if not conversation_id:
                yield json.dumps(
                    {"type": "error", "content": "conversation_id is required to regenerate"}
                )
                return
            conversation = await self._conversation_repo.get_with_messages(conversation_id)
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
        else:
            if not (message or "").strip():
                yield json.dumps({"type": "error", "content": "message is required"})
                return
            message = message.strip()
            if conversation_id:
                conversation = await self._conversation_repo.get_with_messages(
                    conversation_id
                )
                if not conversation:
                    yield json.dumps({"type": "error", "content": "Conversation not found"})
                    return
            else:
                conversation = await self._conversation_repo.create(
                    title=message[:50] + ("..." if len(message) > 50 else "")
                )

        yield json.dumps({"type": "info", "conversation_id": conversation.id})

        cached_response: str | None = None
        if not regenerate:
            query_vector, cached_response = await self._try_semantic_cache(message)
            if cached_response is not None:
                q_score, _ = await evaluate_answer_quality(
                    self._settings,
                    user_query=message,
                    draft_response=cached_response,
                    source="cache",
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

                    yield json.dumps({"type": "status", "content": "Cache hit…"})
                    yield json.dumps({"type": "token", "content": cached_response})
                    yield json.dumps({"type": "status", "content": ""})
                    yield json.dumps({"type": "done"})
                    return
                logger.info(
                    "Stream: cache failed quality (%s); full pipeline",
                    q_score,
                )

        if not skip_user_insert:
            await self._message_repo.add_message(
                conversation_id=conversation.id,
                role="user",
                content=message,
            )

        history_records = await self._message_repo.get_recent_by_conversation(
            conversation.id, limit=HISTORY_CONTEXT_MESSAGE_LIMIT
        )
        liked_messages = await self._message_repo.get_liked_messages(limit=5)
        feedback_context = (
            " | ".join([m.content for m in liked_messages]) if liked_messages else "None"
        )

        reply_text = ""
        tool_calls_made: list[str] = []
        trace_steps: list[dict] = []
        lf_handler = self._make_langfuse_handler()
        callbacks = [lf_handler] if lf_handler else None

        try:
            yield json.dumps({"type": "status", "content": "Preparing context…"})

            agent_input = self._agent_state_payload(
                conversation, message, history_records, feedback_context
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
                kind = event["event"]

                if kind == "on_chain_start":
                    meta = event.get("metadata") or {}
                    node_name = meta.get("langgraph_node") or event.get("name", "")
                    if node_name == "synthesizer":
                        reply_text = ""
                    if node_name == "summarize_history":
                        yield json.dumps({"type": "status", "content": "Summarizing history…"})
                    elif node_name == "optimize_prompt":
                        yield json.dumps({"type": "status", "content": "Optimizing prompt…"})
                    elif node_name == "tools_phase":
                        yield json.dumps({"type": "status", "content": "Looking up movies…"})
                    elif node_name == "synthesizer":
                        yield json.dumps({"type": "status", "content": "Writing reply…"})
                    elif node_name == "quality_eval":
                        yield json.dumps({"type": "status", "content": "Checking quality…"})

                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    yield json.dumps({"type": "status", "content": f"Tool: {tool_name}…"})
                    tool_calls_made.append(tool_name)

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
                await self._redis_repo.store_query(message, reply_text, query_vector)

        yield json.dumps({"type": "done"})

    async def get_conversation(self, conversation_id: str) -> ConversationDetail:
        conversation = await self._conversation_repo.get_with_messages(conversation_id)
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
        self, offset: int = 0, limit: int = 20
    ) -> list[ConversationSummary]:
        conversations = await self._conversation_repo.list_conversations(offset, limit)
        return [
            ConversationSummary(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                message_count=len(c.messages),
            )
            for c in conversations
        ]

    async def delete_conversation(self, conversation_id: str) -> None:
        conversation = await self._conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundException("Conversation", conversation_id)
        await self._conversation_repo.delete(conversation)
        logger.info(f"Conversation deleted: {conversation_id}")

    async def submit_feedback(self, message_id: str, is_liked: bool):
        message = await self._message_repo.set_message_feedback(message_id, is_liked)
        if not message:
            raise NotFoundException("Message", message_id)
        return message
