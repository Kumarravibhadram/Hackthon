from pathlib import Path
import re
import sys

import httpx
from docx import Document

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import settings


SOURCE = Path(r"C:\Users\Ravikumar\Downloads\Jira_User_Stories_Bank_AI_Workspace.docx")
PROJECT_KEY = "BAIW"
LABELS = ["ai-agent", "jira-agent", "bank-ai-workspace"]
MVP_IDS = {"JIRA-01", "JIRA-02", "JIRA-04", "JIRA-05", "JIRA-08"}
TASK_NAMES = {
    "JIRA-01": "Implement Confluence BRD retrieval",
    "JIRA-02": "Implement requirement extraction pipeline",
    "JIRA-04": "Implement AI user-story generation",
    "JIRA-05": "Implement acceptance-criteria generation",
    "JIRA-08": "Implement Jira issue creation API",
}


def adf(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in text.splitlines()
            if line.strip()
        ],
    }


def parse_stories() -> dict[str, dict[str, str]]:
    paragraphs = [paragraph.text.strip() for paragraph in Document(SOURCE).paragraphs]
    stories: dict[str, dict[str, str]] = {}
    index = 0
    while index < len(paragraphs):
        heading = re.match(r"^(JIRA-\d+)\s+[—-]\s+(.+)$", paragraphs[index])
        if not heading:
            index += 1
            continue

        story_id, summary = heading.groups()
        user_story = paragraphs[index + 1].removeprefix("User Story: ").strip()
        criteria: list[str] = []
        cursor = index + 3
        while cursor < len(paragraphs) and not paragraphs[cursor].startswith("Suggested labels:"):
            criteria.append(paragraphs[cursor])
            cursor += 1
        labels = paragraphs[cursor].removeprefix("Suggested labels: ").split(", ")
        stories[story_id] = {
            "summary": summary,
            "user_story": user_story,
            "criteria": criteria,
            "labels": labels,
        }
        index = cursor + 1
    return stories


def main() -> None:
    stories = parse_stories()
    selected = [stories[story_id] | {"id": story_id} for story_id in sorted(MVP_IDS, key=lambda value: int(value.split("-")[1]))]
    base = settings.jira_base_url.rstrip("/")
    auth = (settings.jira_email, settings.jira_api_token)
    client = httpx.Client(auth=auth, timeout=30.0)

    existing = client.get(
        f"{base}/rest/api/3/search/jql",
        params={"jql": f"project = {PROJECT_KEY}", "maxResults": 100, "fields": "summary"},
    )
    existing.raise_for_status()
    if existing.json().get("issues"):
        raise RuntimeError("BAIW is not empty; refusing to create duplicate issues.")

    types = client.get(f"{base}/rest/api/3/project/{PROJECT_KEY}/statuses")
    types.raise_for_status()
    issue_types = {item["name"]: item["id"] for item in types.json()}
    story_type = issue_types["Story"]
    task_type = issue_types["Task"]
    created_stories: dict[str, str] = {}

    for story in selected:
        description = (
            f"User Story:\n{story['user_story']}\n\n"
            "Acceptance Criteria:\n"
            + "\n".join(f"{number}. {criterion}" for number, criterion in enumerate(story["criteria"], 1))
            + f"\n\nTraceability:\n- Source Document: {SOURCE.name}\n- Source Story ID: {story['id']}"
        )
        response = client.post(
            f"{base}/rest/api/3/issue",
            json={
                "fields": {
                    "project": {"key": PROJECT_KEY},
                    "issuetype": {"id": story_type},
                    "summary": story["summary"],
                    "description": adf(description),
                    "priority": {"name": "High"},
                    "labels": LABELS,
                }
            },
        )
        response.raise_for_status()
        created_stories[story["id"]] = response.json()["key"]

    created_tasks: dict[str, str] = {}
    for story_id, task_summary in TASK_NAMES.items():
        story_key = created_stories[story_id]
        response = client.post(
            f"{base}/rest/api/3/issue",
            json={
                "fields": {
                    "project": {"key": PROJECT_KEY},
                    "issuetype": {"id": task_type},
                    "summary": task_summary,
                    "description": adf(
                        f"Technical description:\nImplement the technical work required for {task_summary.lower()}.\n\n"
                        f"Expected outcome:\nThe capability is available for the linked Story {story_key}.\n\n"
                        f"Parent/linked Story: {story_key}\nSource Story ID: {story_id}"
                    ),
                    "priority": {"name": "High"},
                    "labels": LABELS,
                }
            },
        )
        response.raise_for_status()
        task_key = response.json()["key"]
        created_tasks[story_id] = task_key
        link_response = client.post(
            f"{base}/rest/api/3/issueLink",
            json={"type": {"name": "Relates"}, "inwardIssue": {"key": task_key}, "outwardIssue": {"key": story_key}},
        )
        link_response.raise_for_status()

    verify = client.get(
        f"{base}/rest/api/3/search/jql",
        params={"jql": f"project = {PROJECT_KEY}", "maxResults": 100, "fields": "summary,issuetype,issuelinks"},
    )
    verify.raise_for_status()
    issues = verify.json().get("issues", [])
    stories_count = sum(issue["fields"]["issuetype"]["name"] == "Story" for issue in issues)
    tasks_count = sum(issue["fields"]["issuetype"]["name"] == "Task" for issue in issues)
    if stories_count != 5 or tasks_count != 5:
        raise RuntimeError(f"Validation failed: {stories_count} Stories and {tasks_count} Tasks found.")

    print(f"Project: {PROJECT_KEY}")
    print("Stories:")
    for story_id, key in created_stories.items():
        print(story_id, key, f"{base}/browse/{key}")
    print("Tasks:")
    for story_id, key in created_tasks.items():
        print(story_id, key, f"{base}/browse/{key} -> {created_stories[story_id]}")


if __name__ == "__main__":
    main()