from backend.integrations.graph_mail import GraphMailClient


def test_graph_mail_uses_mail_scopes_for_authentication(monkeypatch) -> None:
    client = GraphMailClient.__new__(GraphMailClient)
    client._scopes = ["Mail.Read", "Mail.Send"]
    captured: dict[str, object] = {}

    def fake_token(self, scopes):
        captured["scopes"] = scopes
        return "token"

    monkeypatch.setattr("backend.integrations.graph_calendar.GraphCalendarClient._token", fake_token)

    assert client._token() == "token"
    assert captured["scopes"] == ["Mail.Read", "Mail.Send"]