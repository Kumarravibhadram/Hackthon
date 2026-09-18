"""Microsoft Graph mail access using the workspace's delegated token cache."""

from html import unescape
import re
from typing import Any

import httpx

from backend.app.config import settings
from backend.integrations.graph_calendar import GraphCalendarClient, GraphCalendarError


class GraphMailError(RuntimeError):
    """Raised when Microsoft Graph mail access is unavailable."""


def _plain_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(without_tags).split())


class GraphMailClient(GraphCalendarClient):
    """Delegated Microsoft 365 mail client for the signed-in user."""

    def __init__(self) -> None:
        try:
            super().__init__()
        except GraphCalendarError as exc:
            raise GraphMailError(str(exc)) from exc
        self._scopes = settings.graph_mail_scopes.split()

    def _token(self) -> str:
        return super()._token(self._scopes)

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return super()._request(method, url, **kwargs)
        except GraphCalendarError as exc:
            raise GraphMailError(str(exc)) from exc

    def list_messages(self, *, unread_only: bool = True, limit: int = 10) -> list[dict[str, str]]:
        params = {
            "$top": str(limit),
            "$orderby": "receivedDateTime DESC",
            "$select": "id,subject,from,receivedDateTime,body,importance,isRead,hasAttachments,conversationId",
        }
        if unread_only:
            params["$filter"] = "isRead eq false"

        payload = self._request("GET", "https://graph.microsoft.com/v1.0/me/messages", params=params)
        return [self._message_summary(message) for message in payload.get("value", [])]

    def search_messages(self, query: str, *, limit: int = 10) -> list[dict[str, str]]:
        payload = self._request(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages",
            params={
                "$search": f'"{query}"',
                "$top": str(limit),
                "$select": "id,subject,from,receivedDateTime,body,importance,isRead,hasAttachments,conversationId",
            },
            headers={"ConsistencyLevel": "eventual"},
        )
        return [self._message_summary(message) for message in payload.get("value", [])]

    def list_attachments(self, message_id: str) -> list[dict[str, str]]:
        payload = self._request(
            "GET",
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments",
            params={"$select": "id,name,contentType,size,isInline"},
        )
        return [
            {
                "id": attachment.get("id", ""),
                "name": attachment.get("name", "(unnamed attachment)"),
                "content_type": attachment.get("contentType", ""),
                "size": str(attachment.get("size", 0)),
            }
            for attachment in payload.get("value", [])
        ]

    def send_message(self, recipient: str, subject: str, body: str) -> None:
        self._request(
            "POST",
            "https://graph.microsoft.com/v1.0/me/sendMail",
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": recipient}}],
                },
                "saveToSentItems": True,
            },
        )

    def reply(self, message_id: str, comment: str) -> None:
        self._request(
            "POST",
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply",
            json={"comment": comment},
        )

    def forward(self, message_id: str, recipient: str, comment: str = "") -> None:
        self._request(
            "POST",
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/forward",
            json={"comment": comment, "toRecipients": [{"emailAddress": {"address": recipient}}]},
        )

    def move(self, message_id: str, destination_folder_id: str) -> None:
        self._request(
            "POST",
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move",
            json={"destinationId": destination_folder_id},
        )

    def categorize(self, message_id: str, categories: list[str]) -> None:
        self._request(
            "PATCH",
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
            json={"categories": categories},
        )

    @staticmethod
    def _message_summary(message: dict[str, Any]) -> dict[str, str]:
        sender = message.get("from", {}).get("emailAddress", {})
        return {
            "id": message.get("id", ""),
            "subject": message.get("subject") or "(no subject)",
            "sender": sender.get("name") or sender.get("address") or "Unknown sender",
            "sender_email": sender.get("address", ""),
            "received_at": message.get("receivedDateTime", ""),
            "body": _plain_text(message.get("body", {}).get("content", "")),
            "importance": message.get("importance", ""),
            "is_read": str(message.get("isRead", False)),
            "has_attachments": str(message.get("hasAttachments", False)),
            "attachment_names": "|".join(str(name) for name in message.get("attachmentNames", [])),
            "conversation_id": message.get("conversationId", ""),
        }
