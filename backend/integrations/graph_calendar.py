"""Microsoft Graph calendar access with a persistent delegated token cache."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import httpx

from backend.app.config import settings


class GraphCalendarError(RuntimeError):
    """Raised when Microsoft Graph calendar access is unavailable."""


class GraphCalendarClient:
    def __init__(self) -> None:
        if not settings.graph_client_id:
            raise GraphCalendarError(
                "Microsoft Graph calendar is not configured. Set GRAPH_CLIENT_ID and GRAPH_TENANT_ID."
            )
        self._cache_path = Path(settings.graph_token_cache_path)
        self._scopes = settings.graph_scopes.split()

    def _token(self, scopes: list[str] | None = None) -> str:
        try:
            import msal
        except ImportError as exc:
            raise GraphCalendarError("The msal package is required for Microsoft Graph calendar access.") from exc

        cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            try:
                cache.deserialize(self._cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache = msal.SerializableTokenCache()

        authority = f"https://login.microsoftonline.com/{settings.graph_tenant_id}"
        requested_scopes = scopes or self._scopes
        app = msal.PublicClientApplication(
            settings.graph_client_id,
            authority=authority,
            token_cache=cache,
        )
        accounts = app.get_accounts()
        result = app.acquire_token_silent(requested_scopes, account=accounts[0]) if accounts else None

        if not result:
            flow = app.initiate_device_flow(scopes=requested_scopes)
            if "user_code" not in flow:
                raise GraphCalendarError("Microsoft Graph device authentication could not be started.")
            print(flow["message"])
            result = app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            message = result.get("error_description", "Microsoft Graph authentication failed.")
            raise GraphCalendarError(message)

        if cache.has_state_changed:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(cache.serialize(), encoding="utf-8")
        return result["access_token"]

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        token = self._token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/json"
        try:
            response = httpx.request(method, url, headers=headers, timeout=20.0, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GraphCalendarError("Microsoft Graph calendar request failed.") from exc
        return response.json() if response.content else {}

    def list_events(self, days: int = 7) -> list[dict[str, str]]:
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=days)
        payload = self._request(
            "GET",
            "https://graph.microsoft.com/v1.0/me/calendarView",
            params={
                "startDateTime": start.isoformat().replace("+00:00", "Z"),
                "endDateTime": end.isoformat().replace("+00:00", "Z"),
                "$top": "10",
                "$orderby": "start/dateTime",
            },
            headers={"Prefer": 'outlook.timezone="UTC"'},
        )
        events: list[dict[str, str]] = []
        for event in payload.get("value", []):
            start_text = event.get("start", {}).get("dateTime", "")
            end_text = event.get("end", {}).get("dateTime", "")
            events.append(
                {
                    "subject": event.get("subject") or "(no subject)",
                    "start": _display_datetime(start_text),
                    "end": _display_datetime(end_text),
                    "location": event.get("location", {}).get("displayName", "") or "",
                }
            )
        return events

    def create_event(self, subject: str, start: datetime, duration_minutes: int) -> None:
        end = start + timedelta(minutes=duration_minutes)
        self._request(
            "POST",
            "https://graph.microsoft.com/v1.0/me/events",
            json={
                "subject": subject,
                "start": {"dateTime": start.isoformat(), "timeZone": settings.graph_timezone},
                "end": {"dateTime": end.isoformat(), "timeZone": settings.graph_timezone},
                "isReminderOn": True,
                "reminderMinutesBeforeStart": 15,
            },
        )


def _display_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
