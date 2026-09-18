from datetime import datetime

from backend.integrations.graph_calendar import GraphCalendarClient


def test_graph_calendar_maps_calendar_view_events(monkeypatch) -> None:
    client = GraphCalendarClient.__new__(GraphCalendarClient)
    monkeypatch.setattr(
        client,
        "_request",
        lambda *args, **kwargs: {
            "value": [
                {
                    "subject": "Roadmap review",
                    "start": {"dateTime": "2026-09-16T10:00:00.0000000"},
                    "end": {"dateTime": "2026-09-16T11:00:00.0000000"},
                    "location": {"displayName": "Teams"},
                }
            ]
        },
    )

    events = client.list_events()

    assert events == [
        {
            "subject": "Roadmap review",
            "start": "2026-09-16 10:00",
            "end": "2026-09-16 11:00",
            "location": "Teams",
        }
    ]


def test_graph_calendar_posts_event(monkeypatch) -> None:
    client = GraphCalendarClient.__new__(GraphCalendarClient)
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return {}

    monkeypatch.setattr(client, "_request", fake_request)

    client.create_event("Sprint review", datetime(2026, 9, 16, 14, 0), 45)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/me/events")
    assert captured["json"]["subject"] == "Sprint review"
    assert captured["json"]["end"]["dateTime"] == "2026-09-16T14:45:00"
