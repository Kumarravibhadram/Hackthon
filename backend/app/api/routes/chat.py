"""Chat session endpoints."""

from fastapi import APIRouter

from backend.app.api.schemas.chat import ChatRequest, ChatResponse
from backend.orchestrator.supervisor import supervisor

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def send_message(session_id: str, request: ChatRequest) -> ChatResponse:
    result = supervisor.handle_with_metadata(session_id=session_id, message=request.message, agent=request.agent)
    return ChatResponse(session_id=session_id, answer=result["response"], route=result["route"])
