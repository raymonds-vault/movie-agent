"""
Chat controller — thin API layer for conversation endpoints.
All business logic is delegated to ChatService.
"""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_config, get_db
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
    service: ChatService = Depends(_get_chat_service),
) -> ChatResponse:
    """Process a user message and return the agent's response."""
    return await service.process_message(
        message=request.message,
        conversation_id=request.conversation_id,
    )


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    service: ChatService = Depends(_get_chat_service),
):
    """Real-time streaming chat over WebSocket."""
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        message = data.get("message")
        conversation_id = data.get("conversation_id")
        
        async for chunk in service.stream_message(
            message=message, 
            conversation_id=conversation_id
        ):
            await websocket.send_text(chunk)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        import json
        await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
    finally:
        try:
            await websocket.close()
        except:
            pass


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    summary="List all conversations",
)
async def list_conversations(
    offset: int = 0,
    limit: int = 20,
    service: ChatService = Depends(_get_chat_service),
) -> list[ConversationSummary]:
    """List conversations, most recent first."""
    return await service.list_conversations(offset=offset, limit=limit)


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get conversation with messages",
)
async def get_conversation(
    conversation_id: str,
    service: ChatService = Depends(_get_chat_service),
) -> ConversationDetail:
    """Retrieve a conversation and all its messages."""
    return await service.get_conversation(conversation_id)


@router.delete(
    "/{conversation_id}",
    summary="Delete a conversation",
    status_code=204,
)
async def delete_conversation(
    conversation_id: str,
    service: ChatService = Depends(_get_chat_service),
) -> None:
    """Delete a conversation and all its messages."""
    await service.delete_conversation(conversation_id)

@router.post(
    "/message/{message_id}/feedback",
    summary="Submit user feedback for a message",
)
async def submit_feedback(
    message_id: str,
    request: FeedbackRequest,
    service: ChatService = Depends(_get_chat_service),
) -> dict:
    """Mark a message as liked/disliked."""
    message = await service.submit_feedback(message_id, request.is_liked)
    return {"status": "success", "message_id": message.id, "is_liked": message.is_liked}
