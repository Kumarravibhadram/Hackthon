"""Dashboard endpoints."""

import shutil
import importlib.util
from pathlib import Path

from fastapi import APIRouter

from backend.app.config import settings
from backend.knowledge.loaders import discover_documents

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_summary() -> dict[str, object]:
    knowledge_documents = len(discover_documents(Path("data/knowledge_base")))
    jira_connected = bool(settings.jira_base_url and settings.jira_email and settings.jira_api_token)
    outlook_available = bool(settings.graph_client_id or shutil.which("outlook.exe") or importlib.util.find_spec("win32com.client"))
    teams_available = bool(shutil.which("ms-teams.exe") or shutil.which("teams.exe"))
    confluence_connected = bool(settings.confluence_base_url and settings.jira_email and settings.jira_api_token)
    askbank_available = bool(
        settings.llm_provider.casefold() == "ollama"
        or settings.llm_api_key
        or settings.openai_api_key
    )
    integration_status = {
        "Jira": jira_connected,
        "Outlook": outlook_available,
        "Microsoft Teams": teams_available,
        "Confluence": confluence_connected,
        "AskBank": askbank_available,
        "Knowledge base": knowledge_documents > 0,
    }
    return {
        "status": "ready",
        "connected_integrations": sum(integration_status.values()),
        "integration_status": integration_status,
        "knowledge_documents": knowledge_documents,
    }
