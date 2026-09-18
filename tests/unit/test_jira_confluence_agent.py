from types import SimpleNamespace

from backend.agents.jira_confluence_agent import JiraConfluenceAgent


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "issues": [
                {
                    "key": "DEMO-1",
                    "fields": {
                        "summary": "Fix Jira integration",
                        "project": {"key": "DEMO"},
                        "status": {"name": "To Do"},
                        "assignee": {"displayName": "Ravi"},
                        "updated": "2026-09-15T10:00:00.000+0000",
                    },
                }
            ]
        }


class CreatedResponse:
    status_code = 201

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"key": "DEMO-42"}


def test_jira_agent_uses_supported_jql_search_endpoint(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="DEMO",
    )
    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_jira_information("integration")

    assert request["url"] == "https://example.atlassian.net/rest/api/3/search/jql"
    assert request["params"] == {
        "jql": 'project = DEMO AND (text ~ "integration")',
        "maxResults": 5,
        "fields": "summary,status,assignee,updated,project,description",
    }
    assert request["headers"] == {"Accept": "application/json"}
    assert "| DEMO-1 | Fix Jira integration | DEMO | To Do | Ravi | 2026-09-15 10:00:00 |" in result


def test_jira_agent_uses_assigned_issue_overview_for_generic_jira_request(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    JiraConfluenceAgent()._fetch_jira_information("Show my recently updated Jira issues")

    assert request["params"] == {
        "jql": "assignee = currentUser() ORDER BY updated DESC",
        "maxResults": 5,
        "fields": "summary,status,assignee,updated,project,description",
    }


def test_jira_agent_treats_latest_story_request_as_overview(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    JiraConfluenceAgent()._fetch_jira_information("tell me latest jira story")

    assert request["params"]["jql"] == "assignee = currentUser() ORDER BY updated DESC"


def test_jira_agent_falls_back_to_recent_accessible_project_issues(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    requests: list[dict[str, object]] = []

    class EmptyResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {"issues": []}

    class ProjectsResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {"values": [{"key": "DEMO"}]}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        if url.endswith("/project/search"):
            return ProjectsResponse()
        if len(requests) == 1:
            return EmptyResponse()
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_jira_information("Jira")

    assert requests[1]["url"] == "https://example.atlassian.net/rest/api/3/project/search"
    assert requests[2]["params"] == {
        "jql": "project in (DEMO) ORDER BY updated DESC",
        "maxResults": 5,
        "fields": "summary,status,assignee,updated,project,description",
    }
    assert "| DEMO-1 | Fix Jira integration | DEMO | To Do | Ravi | 2026-09-15 10:00:00 |" in result


def test_jira_agent_creates_task_from_natural_language(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="DEMO",
    )
    request: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> CreatedResponse:
        request["url"] = url
        request.update(kwargs)
        return CreatedResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.post", fake_post)

    result = JiraConfluenceAgent().run(SimpleNamespace(message="Create a task: Add audit logging"))

    assert request["url"] == "https://example.atlassian.net/rest/api/3/issue"
    assert request["json"]["fields"]["project"] == {"key": "DEMO"}
    assert request["json"]["fields"]["issuetype"] == {"name": "Task"}
    assert request["json"]["fields"]["summary"] == "Add audit logging"
    assert "DEMO-42" in result


def test_jira_agent_analyzes_story_text() -> None:
    context = SimpleNamespace(
        message="Analyze story: As a banker, I want to review KYC alerts so that I can approve safe accounts. Given an alert, when I review it, then the decision is recorded."
    )

    result = JiraConfluenceAgent().run(context)

    assert "User story format: Ready" in result
    assert "Acceptance criteria: Present" in result
    assert "Expected behavior: Defined" in result


def test_jira_agent_fetches_confluence_page_content(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    request: dict[str, object] = {}

    class ConfluenceResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "title": "Customer Verification Policy",
                        "id": "101",
                        "body": {"storage": {"value": "<p>Employees must complete two approved identity checks.</p><p>Use a one-time passcode.</p>"}},
                    }
                ]
            }

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return ConfluenceResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_confluence_information("Customer Verification Policy")

    assert request["url"] == "https://example.atlassian.net/rest/api/content/search"
    assert "Customer Verification Policy" in result
    assert "two approved identity checks" in result
    assert "one-time passcode" in result
