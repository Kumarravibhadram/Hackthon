"""Meeting workflow agent."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import subprocess

from backend.agents.base import Agent
from backend.app.config import settings
from backend.core.models import AgentContext
from backend.integrations.graph_calendar import GraphCalendarClient, GraphCalendarError


LOCAL_CALENDAR_PATH = Path("data/workspace_calendar.json")


def _teams_executable() -> str | None:
    return shutil.which("ms-teams.exe") or shutil.which("teams.exe")


def open_teams() -> None:
    executable = _teams_executable()
    if executable:
        subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    raise RuntimeError(
        "Microsoft Teams desktop is unavailable. Open Teams once and sign in there, then retry."
    )


def _outlook_namespace():
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError("Classic Microsoft Outlook is required for desktop calendar access.") from exc

    try:
        pythoncom.CoInitialize()
        dispatch = getattr(win32com.client, "DispatchEx", win32com.client.Dispatch)
        outlook = dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        try:
            namespace.Logon("", "", False, False)
        except Exception:
            pass
        return namespace
    except Exception as exc:
        raise RuntimeError("Classic Outlook could not open the current profile.") from exc


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _read_local_calendar(days: int = 7) -> list[dict[str, str]]:
    if not LOCAL_CALENDAR_PATH.exists():
        return []

    try:
        stored_events = json.loads(LOCAL_CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    start = datetime.now()
    end = start + timedelta(days=days)
    return [
        event
        for event in stored_events
        if isinstance(event, dict)
        and start <= datetime.fromisoformat(event["start"]) <= end
    ]


def _save_local_appointment(subject: str, start: datetime, duration_minutes: int) -> None:
    LOCAL_CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        events = json.loads(LOCAL_CALENDAR_PATH.read_text(encoding="utf-8")) if LOCAL_CALENDAR_PATH.exists() else []
    except (OSError, json.JSONDecodeError):
        events = []

    end = start + timedelta(minutes=duration_minutes)
    events.append(
        {
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "location": "Workspace calendar",
        }
    )
    LOCAL_CALENDAR_PATH.write_text(json.dumps(events, indent=2), encoding="utf-8")

def read_outlook_calendar(days: int = 7) -> list[dict[str, str]]:
    if settings.allow_outlook_fallback:
        try:
            namespace = _outlook_namespace()
            calendar = namespace.GetDefaultFolder(9)
            items = calendar.Items
            items.Sort("[Start]")
            items.IncludeRecurrences = True
            start = datetime.now()
            end = start + timedelta(days=days)
            events: list[dict[str, str]] = []

            for item in list(items):
                event_start = _normalize_datetime(getattr(item, "Start", None))
                if event_start is None or not hasattr(event_start, "year") or not start <= event_start <= end:
                    continue
                event_end = _normalize_datetime(getattr(item, "End", event_start)) or event_start
                events.append(
                    {
                        "subject": getattr(item, "Subject", "(no subject)"),
                        "start": event_start.strftime("%Y-%m-%d %H:%M"),
                        "end": event_end.strftime("%Y-%m-%d %H:%M"),
                        "location": getattr(item, "Location", "") or "",
                    }
                )
                if len(events) >= 10:
                    break
            if events:
                return events
        except RuntimeError:
            pass

    if settings.graph_client_id:
        try:
            return GraphCalendarClient().list_events(days)
        except GraphCalendarError as exc:
            raise RuntimeError(str(exc)) from exc

    local_events = _read_local_calendar(days)
    if local_events:
        return local_events
    raise RuntimeError(
        "Classic Microsoft Outlook is required for desktop calendar access. Open Outlook and sign in, "
        "or schedule the meeting through the workspace calendar."
    )


def create_outlook_appointment(subject: str, start: datetime, duration_minutes: int) -> None:
    if settings.allow_outlook_fallback:
        try:
            import win32com.client
            outlook = win32com.client.Dispatch("Outlook.Application")
            appointment = outlook.CreateItem(1)
            appointment.Subject = subject
            appointment.Start = start
            appointment.End = start + timedelta(minutes=duration_minutes)
            appointment.Duration = duration_minutes
            appointment.Location = "Microsoft Teams"
            appointment.BusyStatus = 2
            appointment.ReminderSet = True
            appointment.Body = "Created by Northstar Bank Workspace."
            appointment.Save()
            return
        except Exception:  # fallback to Graph or workspace calendar below
            pass

    if settings.graph_client_id:
        try:
            GraphCalendarClient().create_event(subject, start, duration_minutes)
            return
        except GraphCalendarError as graph_error:
            raise RuntimeError(str(graph_error)) from graph_error

    _save_local_appointment(subject, start, duration_minutes)


class MeetingAgent(Agent):
    name = "meeting"

    def run(self, context: AgentContext) -> str:
        prompt = context.message.strip() or "your request"
        if any(
            term in prompt.lower()
            for term in ("open teams", "open microsoft teams", "launch teams", "launch microsoft teams", "start teams")
        ):
            try:
                open_teams()
            except RuntimeError as exc:
                return str(exc)
            return "Microsoft Teams is open and ready for your meeting request."

        prompt_lower = prompt.lower()
        if any(term in prompt_lower for term in ("calendar", "upcoming meeting", "upcoming event", "schedule")):
            schedule_match = re.match(r"schedule meeting:\s*(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*\|\s*(\d+)", prompt, re.IGNORECASE)
            if schedule_match:
                subject, start_text, duration_text = schedule_match.groups()
                start = datetime.strptime(start_text, "%Y-%m-%d %H:%M")
                duration = int(duration_text)
                try:
                    create_outlook_appointment(subject, start, duration)
                except RuntimeError as exc:
                    if settings.graph_client_id:
                        return f"Calendar event could not be created: {exc}"
                    _save_local_appointment(subject, start, duration)
                    return f"Calendar event \"{subject}\" was saved to the workspace calendar."
                except ValueError as exc:
                    return f"Calendar event could not be created: {exc}"
                return f"Calendar event \"{subject}\" was created in Outlook."

            try:
                events = read_outlook_calendar()
            except RuntimeError as exc:
                return str(exc)
            if not events:
                return "No upcoming calendar events were found in the next 7 days."
            lines = ["Upcoming Outlook calendar events:"]
            for event in events:
                location = f" | {event['location']}" if event["location"] else ""
                lines.append(f"- {event['start']} to {event['end']} | {event['subject']}{location}")
            return "\n".join(lines)

        return (
            f"Meeting workflow is ready for \"{prompt}\". Teams and the Outlook calendar are available locally."
        )
