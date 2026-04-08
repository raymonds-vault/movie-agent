"""
Chat controller — thin API layer for conversation endpoints.
All business logic is delegated to ChatService.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionLocal
from app.core.dependencies import (
    get_config,
    get_current_user,
    get_current_user_optional,
    get_db,
    resolve_chat_user_from_id_token,
)
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])


def _get_chat_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_config),
) -> ChatService:
    """Dependency: inject ChatService with its dependencies."""
    return ChatService(session=db, settings=settings)


@router.post(
    "",
    response_model=ChatResponse,
    summary="Send a message to the movie agent",
    description="Send a message and receive an AI response. "
    "Omit conversation_id to start a new conversation.",
)
async def chat(
    request: ChatRequest,
    current_user: User | None = Depends(get_current_user_optional),
    service: ChatService = Depends(_get_chat_service),
) -> ChatResponse:
    """Process a user message and return the agent's response."""
    return await service.process_message(
        message=request.message,
        conversation_id=request.conversation_id,
        user_id=current_user.id if current_user else None,
    )


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    """Real-time streaming chat. Optional ``id_token`` for authenticated users; omit for anonymous."""
    await websocket.accept()
    settings = get_settings()
    try:
        data = await websocket.receive_json()
    except WebSocketDisconnect:
        return

    id_token = data.get("id_token")
    message = data.get("message")
    conversation_id = data.get("conversation_id")
    regenerate = bool(data.get("regenerate"))

    async with AsyncSessionLocal() as session:
        try:
            user = await resolve_chat_user_from_id_token(session, settings, id_token)
        except HTTPException as e:
            detail = e.detail
            text = detail if isinstance(detail, str) else json.dumps(detail)
            await websocket.send_text(json.dumps({"type": "error", "content": text}))
            await websocket.close(code=4401)
            return
        try:
            service = ChatService(session=session, settings=settings)
            async for chunk in service.stream_message(
                message=message,
                conversation_id=conversation_id,
                user_id=user.id if user else None,
                regenerate=regenerate,
            ):
                await websocket.send_text(chunk)
            await session.commit()
        except WebSocketDisconnect:
            await session.rollback()
        except Exception as e:
            await session.rollback()
            try:
                await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
            except Exception:
                pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    summary="List all conversations",
)
async def list_conversations(
    offset: int = 0,
    limit: int = 20,
    current_user: User | None = Depends(get_current_user_optional),
    service: ChatService = Depends(_get_chat_service),
) -> list[ConversationSummary]:
    """List conversations, most recent first."""
    return await service.list_conversations(
        current_user.id if current_user else None,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get conversation with messages",
)
async def get_conversation(
    conversation_id: str,
    current_user: User | None = Depends(get_current_user_optional),
    service: ChatService = Depends(_get_chat_service),
) -> ConversationDetail:
    """Retrieve a conversation and all its messages."""
    return await service.get_conversation(
        conversation_id,
        user_id=current_user.id if current_user else None,
    )


@router.delete(
    "/{conversation_id}",
    summary="Delete a conversation",
    status_code=204,
)
async def delete_conversation(
    conversation_id: str,
    current_user: User | None = Depends(get_current_user_optional),
    service: ChatService = Depends(_get_chat_service),
) -> None:
    """Delete a conversation and all its messages."""
    await service.delete_conversation(
        conversation_id,
        user_id=current_user.id if current_user else None,
    )


@router.post(
    "/message/{message_id}/feedback",
    summary="Submit user feedback for a message",
)
async def submit_feedback(
    message_id: str,
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    service: ChatService = Depends(_get_chat_service),
) -> dict:
    """Mark a message as liked/disliked."""
    message = await service.submit_feedback(
        message_id, request.is_liked, user_id=current_user.id
    )
    return {"status": "success", "message_id": message.id, "is_liked": message.is_liked}


@router.get("/analytics/tool-usage", summary="Tool usage analytics")
async def tool_usage_stats(
    tool_name: str | None = None,
    current_user: User | None = Depends(get_current_user_optional),
    service: ChatService = Depends(_get_chat_service),
) -> list[dict]:
    return await service.get_tool_usage_stats(
        tool_name=tool_name,
        user_id=current_user.id if current_user else None,
    )


@router.get("/analytics/run-failures", summary="Run step failure breakdown")
async def run_failure_breakdown(
    current_user: User | None = Depends(get_current_user_optional),
    service: ChatService = Depends(_get_chat_service),
) -> list[dict]:
    return await service.get_run_failure_breakdown(
        user_id=current_user.id if current_user else None,
    )


@router.get("/analytics/cache-decisions", summary="Semantic cache decision stats")
async def cache_decision_stats(
    current_user: User | None = Depends(get_current_user_optional),
    service: ChatService = Depends(_get_chat_service),
) -> list[dict]:
    return await service.get_cache_decision_stats(
        user_id=current_user.id if current_user else None,
    )
