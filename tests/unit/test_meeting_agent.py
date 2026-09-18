from backend.agents.meeting_agent import MeetingAgent
from backend.core.models import AgentContext


def test_meeting_agent_opens_teams(monkeypatch) -> None:
    opened: list[bool] = []
    monkeypatch.setattr("backend.agents.meeting_agent.open_teams", lambda: opened.append(True))

    result = MeetingAgent().run(AgentContext(session_id="session-8", message="Open Microsoft Teams"))

    assert opened == [True]
    assert "Teams is open" in result


def test_meeting_agent_lists_upcoming_calendar_events(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.meeting_agent.read_outlook_calendar",
        lambda: [{"subject": "Roadmap review", "start": "2026-09-16 10:00", "end": "2026-09-16 11:00", "location": "Teams"}],
    )

    result = MeetingAgent().run(AgentContext(session_id="session-9", message="Show upcoming meetings"))

    assert "Upcoming Outlook calendar events" in result
    assert "Roadmap review" in result


def test_meeting_agent_creates_calendar_event(monkeypatch) -> None:
    created: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "backend.agents.meeting_agent.create_outlook_appointment",
        lambda subject, start, duration: created.append((subject, duration)),
    )

    result = MeetingAgent().run(
        AgentContext(session_id="session-10", message="Schedule meeting: Sprint review | 2026-09-16 14:00 | 45")
    )

    assert created == [("Sprint review", 45)]
    assert "was created in Outlook" in result


def test_meeting_agent_uses_local_calendar_when_outlook_is_unavailable(monkeypatch, tmp_path) -> None:
    calendar_path = tmp_path / "workspace_calendar.json"
    monkeypatch.setattr("backend.agents.meeting_agent.LOCAL_CALENDAR_PATH", calendar_path)
    monkeypatch.setattr(
        "backend.agents.meeting_agent._outlook_namespace",
        lambda: (_ for _ in ()).throw(RuntimeError("Classic Outlook could not open the current profile.")),
    )

    result = MeetingAgent().run(AgentContext(session_id="session-11", message="Show upcoming meetings"))

    assert "Classic Microsoft Outlook is required" in result


def test_meeting_agent_saves_scheduled_event_to_local_calendar(monkeypatch, tmp_path) -> None:
    calendar_path = tmp_path / "workspace_calendar.json"
    monkeypatch.setattr("backend.agents.meeting_agent.LOCAL_CALENDAR_PATH", calendar_path)
    monkeypatch.setattr(
        "backend.agents.meeting_agent.create_outlook_appointment",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Outlook profile unavailable")),
    )

    result = MeetingAgent().run(
        AgentContext(session_id="session-12", message="Schedule meeting: Sprint review | 2026-09-16 14:00 | 45")
    )

    assert result == 'Calendar event "Sprint review" was saved to the workspace calendar.'
    assert calendar_path.exists()