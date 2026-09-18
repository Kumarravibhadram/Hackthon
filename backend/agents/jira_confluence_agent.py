"""Jira and Confluence workflow agent."""

from __future__ import annotations

import re
from typing import Any

import httpx

from backend.agents.base import Agent
from backend.app.config import settings
from backend.core.models import AgentContext


class JiraConfluenceAgent(Agent):
    name = "jira_confluence"

    def run(self, context: AgentContext) -> str:
        query = context.message.strip() or "recent project activity"
        action = self._parse_create_request(query)
        if action:
            return self._create_issue(action[0], action[1])

        if self._is_story_analysis_request(query):
            return self._analyze_story(query)

        parts: list[str] = []

        confluence_payload = self._fetch_confluence_information(query)
        if confluence_payload:
            parts.append(confluence_payload)

        jira_payload = self._fetch_jira_information(query)
        if jira_payload:
            parts.append(jira_payload)

        ourtool_payload = self._fetch_ourtool_information(query)
        if ourtool_payload:
            parts.append(ourtool_payload)

        if parts:
            return "\n\n".join(parts)

        return (
            "Live Jira, Confluence, or OurTool information is unavailable because the required "
            "external integration settings are not configured. Add JIRA_BASE_URL, JIRA_EMAIL, "
            "JIRA_API_TOKEN, JIRA_PROJECT_KEY, CONFLUENCE_BASE_URL, OURTOOL_BASE_URL, and OURTOOL_API_KEY to the environment."
        )

    @staticmethod
    def _parse_create_request(query: str) -> tuple[str, str] | None:
        match = re.match(
            r"^\s*(?:please\s+)?create\s+(?:a\s+)?(task|user\s+story|story)"
            r"(?:\s+in\s+jira)?\s*[:\-]?\s*(.+?)\s*$",
            query,
            flags=re.IGNORECASE,
        )
        if not match or not match.group(2).strip():
            return None
        issue_type = "Task" if match.group(1).casefold() == "task" else "Story"
        return issue_type, match.group(2).strip()

    def _create_issue(self, issue_type: str, summary: str) -> str:
        if not settings.jira_base_url or not settings.jira_api_token or not settings.jira_email:
            return "Jira creation is unavailable. Configure JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
        if not settings.jira_project_key:
            return "Jira creation is unavailable because JIRA_PROJECT_KEY is not configured."

        try:
            response = httpx.post(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token),
                json={
                    "fields": {
                        "project": {"key": settings.jira_project_key},
                        "summary": summary,
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": summary}],
                                }
                            ],
                        },
                        "issuetype": {"name": issue_type},
                    }
                },
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            issue_key = payload.get("key", "the new issue")
            return f"Jira {issue_type} created successfully: {issue_key} - {summary}"
        except httpx.HTTPStatusError as error:
            return f"Jira issue creation failed (HTTP {error.response.status_code})."
        except httpx.HTTPError:
            return "Jira issue creation failed because Jira could not be reached."

    @staticmethod
    def _is_story_analysis_request(query: str) -> bool:
        normalized = query.casefold()
        return "analy" in normalized and "stor" in normalized

    def _analyze_story(self, query: str) -> str:
        issue_key_match = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", query)
        story_text = query
        if issue_key_match and settings.jira_base_url and settings.jira_api_token and settings.jira_email:
            try:
                response = httpx.get(
                    f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key_match.group(1)}",
                    params={"fields": "summary,description,issuetype"},
                    headers={"Accept": "application/json"},
                    auth=(settings.jira_email, settings.jira_api_token),
                    timeout=10.0,
                )
                response.raise_for_status()
                fields = response.json().get("fields", {})
                story_text = f"{fields.get('summary', '')} {self._flatten_description(fields.get('description'))}"
            except httpx.HTTPError:
                return f"Jira story analysis failed because {issue_key_match.group(1)} could not be loaded."
        elif issue_key_match:
            return "Jira story analysis needs Jira credentials to load the requested issue."

        return self._format_story_analysis(story_text)

    @staticmethod
    def _flatten_description(description: Any) -> str:
        if isinstance(description, str):
            return description
        if not isinstance(description, dict):
            return ""
        text: list[str] = []
        for block in description.get("content", []):
            for item in block.get("content", []):
                if item.get("text"):
                    text.append(item["text"])
        return " ".join(text)

    @staticmethod
    def _format_story_analysis(story_text: str) -> str:
        normalized = " ".join(story_text.split())
        has_user_story = bool(re.search(r"\bas\s+(?:a|an|the)\b.+\bi\s+(?:want|need)\b.+\bso\s+that\b", normalized, re.IGNORECASE))
        has_acceptance = bool(re.search(r"acceptance criteria|given\b.+when\b.+then\b", normalized, re.IGNORECASE))
        has_action = bool(re.search(r"must|should|can|shall", normalized, re.IGNORECASE))
        gaps = []
        if not has_user_story:
            gaps.append("Use an As a / I want / So that statement")
        if not has_acceptance:
            gaps.append("Add Given / When / Then acceptance criteria")
        if not has_action:
            gaps.append("Define the expected behavior or outcome")
        result = [
            "Jira story analysis:",
            f"- User story format: {'Ready' if has_user_story else 'Needs improvement'}",
            f"- Acceptance criteria: {'Present' if has_acceptance else 'Missing'}",
            f"- Expected behavior: {'Defined' if has_action else 'Unclear'}",
        ]
        result.append("- Recommended next steps: " + ("; ".join(gaps) if gaps else "Ready for refinement and estimation"))
        return "\n".join(result)

    def _fetch_confluence_information(self, query: str) -> str:
        base_url = (getattr(settings, "confluence_base_url", "") or settings.jira_base_url or "").rstrip("/")
        if not base_url:
            return ""

        title_query = query.strip()
        if not title_query:
            return ""

        try:
            response = httpx.get(
                f"{base_url}/rest/api/content/search",
                params={"cql": f'title ~ "{title_query}" OR text ~ "{title_query}"', "limit": 3},
                headers={"Accept": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token) if settings.jira_email and settings.jira_api_token else None,
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", [])
            if not results:
                return "Confluence: No matching pages were found for the provided request."

            lines: list[str] = ["### Confluence Pages"]
            for result in results[:3]:
                title = str(result.get("title") or "Untitled page")
                page_id = result.get("id", "")
                text = self._extract_confluence_text(result)
                lines.append(f"- {title} (Page ID: {page_id})")
                if text:
                    lines.append(text[:500] + ("..." if len(text) > 500 else ""))
            return "\n".join(lines)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 401:
                return (
                    "Confluence: Access denied (401). Verify that your Atlassian account has Confluence access "
                    "and set CONFLUENCE_BASE_URL to the Confluence site if it is different from JIRA_BASE_URL."
                )
            return f"Confluence: Live Confluence data could not be retrieved (HTTP {error.response.status_code})."
        except httpx.HTTPError:
            return "Confluence: Live Confluence data could not be retrieved right now."

    @staticmethod
    def _extract_confluence_text(result: dict[str, Any]) -> str:
        body = result.get("body") or {}
        storage = body.get("storage") or {}
        value = storage.get("value") or ""
        if not value:
            return ""
        text = re.sub(r"<[^>]+>", " ", value)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _fetch_jira_information(self, query: str) -> str:
        if not settings.jira_base_url or not settings.jira_api_token or not settings.jira_email:
            return ""

        try:
            search_jql = self._build_jira_query(query)
            if settings.jira_project_key:
                search_jql = f'project = {settings.jira_project_key} AND ({search_jql})'

            response = httpx.get(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql",
                params={
                    "jql": search_jql,
                    "maxResults": 5,
                    "fields": "summary,status,assignee,updated,project,description",
                },
                headers={"Accept": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token),
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            issues = payload.get("issues", [])
            if not issues and self._is_overview_query(query):
                issues = self._fetch_recent_accessible_issues()
            if not issues:
                return "Jira: No matching issues were found for the provided request."

            return self._format_jira_issues(issues[:5], sort_results=not self._is_overview_query(query))
        except httpx.HTTPStatusError as error:
            return f"Jira: Live Jira data could not be retrieved (HTTP {error.response.status_code})."
        except httpx.HTTPError:
            return "Jira: Live Jira data could not be retrieved right now."

    @staticmethod
    def _format_jira_issues(issues: list[dict[str, Any]], sort_results: bool = True) -> str:
        rows: list[tuple[str, str, str, str, str, str]] = []
        for issue in issues:
            fields = issue.get("fields", {})
            assignee = fields.get("assignee") or {}
            project = fields.get("project") or {}
            status = fields.get("status") or {}
            rows.append(
                (
                    str(issue.get("key") or "N/A"),
                    str(fields.get("summary") or "N/A"),
                    str(project.get("key") or "N/A"),
                    str(status.get("name") or "N/A"),
                    str(assignee.get("displayName") or "N/A"),
                    JiraConfluenceAgent._format_timestamp(fields.get("updated")),
                )
            )

        if sort_results:
            rows.sort(key=lambda row: row[0])
        lines = [
            f"### Jira Issues — {len(rows)} Results",
            "",
            "| Issue Key | Summary | Project | Status | Assignee | Updated |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        lines.extend(f"| {' | '.join(row)} |" for row in rows)
        return "\n".join(lines)

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        if not value:
            return "N/A"
        timestamp = str(value)
        match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", timestamp)
        return match.group(1).replace("T", " ") if match else timestamp

    @staticmethod
    def _build_jira_query(query: str) -> str:
        if JiraConfluenceAgent._is_overview_query(query):
            return "assignee = currentUser() ORDER BY updated DESC"

        return f'text ~ "{query}"'

    @staticmethod
    def _is_overview_query(query: str) -> bool:
        normalized_query = " ".join(query.casefold().split())
        if normalized_query in {
            "jira",
            "jira issues",
            "show jira issues",
            "show my jira issues",
            "show my recently updated jira issues",
            "recent project activity",
        }:
            return True

        has_jira_subject = (
            "jira" in normalized_query
            or "issue" in normalized_query
            or "story" in normalized_query
            or "task" in normalized_query
            or "backlog" in normalized_query
            or "work item" in normalized_query
        )
        has_recent_marker = any(marker in normalized_query for marker in ("latest", "recent", "newest", "updated"))
        return has_jira_subject and has_recent_marker

    def _fetch_recent_accessible_issues(self) -> list[dict[str, Any]]:
        """Return recent issues from projects visible to the authenticated user."""
        try:
            base_url = settings.jira_base_url.rstrip("/")
            auth = (settings.jira_email, settings.jira_api_token)
            projects_response = httpx.get(
                f"{base_url}/rest/api/3/project/search",
                params={"maxResults": 50},
                headers={"Accept": "application/json"},
                auth=auth,
                timeout=10.0,
            )
            projects_response.raise_for_status()
            project_keys = [
                project.get("key")
                for project in projects_response.json().get("values", [])
                if project.get("key")
            ]
            if not project_keys:
                return []

            project_jql = f"project in ({', '.join(project_keys)}) ORDER BY updated DESC"
            issues_response = httpx.get(
                f"{base_url}/rest/api/3/search/jql",
                params={
                    "jql": project_jql,
                    "maxResults": 5,
                    "fields": "summary,status,assignee,updated,project,description",
                },
                headers={"Accept": "application/json"},
                auth=auth,
                timeout=10.0,
            )
            issues_response.raise_for_status()
            return issues_response.json().get("issues", [])
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    def _fetch_ourtool_information(self, query: str) -> str:
        if not settings.ourtool_base_url:
            return ""

        try:
            request_url = settings.ourtool_base_url.rstrip("/")
            separator = "&" if "?" in request_url else "?"
            request_url = f"{request_url}{separator}q={query}"

            headers: dict[str, str] = {"Accept": "application/json"}
            if settings.ourtool_api_key:
                headers["Authorization"] = f"Bearer {settings.ourtool_api_key}"

            response = httpx.get(request_url, headers=headers, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
            return self._format_tools_payload(payload)
        except Exception:
            return "OurTool: Live external tool data could not be retrieved right now."

    def _format_tools_payload(self, payload: Any) -> str:
        if isinstance(payload, dict):
            if "items" in payload and isinstance(payload["items"], list):
                items = payload["items"]
            elif "results" in payload and isinstance(payload["results"], list):
                items = payload["results"]
            else:
                items = [payload]
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        if not items:
            return "OurTool: No matching items were returned by the connected tool."

        lines = ["OurTool exact results:"]
        for item in items[:5]:
            if isinstance(item, dict):
                title = item.get("title") or item.get("name") or item.get("id") or "Untitled"
                description = item.get("description") or item.get("summary") or item.get("status") or "No additional detail"
                lines.append(f"- {title}: {description}")
            else:
                lines.append(f"- {item}")

        return "\n".join(lines)
