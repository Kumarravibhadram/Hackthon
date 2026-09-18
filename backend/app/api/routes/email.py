"""Email actions backed by the local Outlook desktop profile."""

from fastapi import APIRouter, HTTPException, Query

from backend.agents.email_agent import list_mailbox_messages, send_outlook_email, _priority
from backend.app.api.schemas.chat import EmailSendRequest

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/messages")
def list_messages(
    unread_only: bool = Query(True),
    query: str = Query(""),
) -> dict[str, object]:
    messages = list_mailbox_messages(unread_only=unread_only, search_query=query.strip())
    if messages is None:
        raise HTTPException(status_code=503, detail="Mailbox is unavailable. Check the Outlook profile or Microsoft Graph sign-in.")

    normalized = []
    for message in messages:
        normalized.append(
            {
                "id": str(message.get("id", "")),
                "subject": str(message.get("subject", "(no subject)")),
                "sender": str(message.get("sender", "Unknown sender")),
                "sender_email": str(message.get("sender_email", "")),
                "received_at": str(message.get("received_at", "")),
                "body": str(message.get("body", "")),
                "priority": _priority(message),
                "has_attachments": str(message.get("has_attachments", "false")).lower() == "true",
                "attachment_names": [name for name in str(message.get("attachment_names", "")).split("|") if name],
            }
        )
    return {"messages": normalized}


@router.post("/send")
def send_email(request: EmailSendRequest) -> dict[str, str]:
    try:
        provider = send_outlook_email(request.recipient, request.subject, request.body)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "sent", "recipient": request.recipient, "provider": provider}