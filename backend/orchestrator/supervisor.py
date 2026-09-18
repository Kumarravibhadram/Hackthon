"""LangGraph supervisor for the employee request workflow."""

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.assistant_agent import AssistantAgent
from backend.agents.chat_agent import ChatAgent
from backend.agents.document_agent import DocumentAgent
from backend.agents.email_agent import EmailAgent
from backend.agents.jira_confluence_agent import JiraConfluenceAgent
from backend.agents.meeting_agent import MeetingAgent
from backend.knowledge.retriever import KnowledgeRetriever


class SupervisorState(TypedDict, total=False):
    session_id: str
    message: str
    agent: str | None
    route: str
    agent_name: str
    sources: list[str]
    passages: list[str]
    response: str


def classify_request(state: SupervisorState) -> SupervisorState:
    requested_agent = (state.get("agent") or "").casefold()
    explicit_routes = {
        "email": "email",
        "meeting": "meeting",
        "jira": "jira_confluence",
        "confluence": "confluence",
        "document": "document",
        "knowledge": "document",
        "assistant": "assistant",
    }
    if requested_agent in explicit_routes:
        return {"route": explicit_routes[requested_agent]}

    message = state["message"].lower()

    if any(term in message for term in ("email", "outlook", "mailmate", "mailbox", "inbox", "send", "reply", "draft")) or re.search(
        r"\b(?:read|show|find|check)\s+(?:my\s+)?(?:latest|newest|recent)\s+mail\b",
        message,
    ):
        route = "email"
    elif any(term in message for term in ("meeting", "calendar", "teams", "schedule", "agenda")):
        route = "meeting"
    elif any(term in message for term in ("jira", "confluence", "issue", "sprint", "roadmap", "project", "ourtool")) or (
        any(term in message for term in ("recent", "latest", "newest", "updated"))
        and any(term in message for term in ("task", "tasks", "backlog", "work item", "work items"))
    ):
        route = "jira_confluence"
    elif any(term in message for term in ("document", "file", "policy", "policies", "contract", "verification")):
        route = "document"
    else:
        route = "assistant"

    return {"route": route}


def retrieve_knowledge(state: SupervisorState) -> SupervisorState:
    if state.get("route") == "assistant" or (
        state.get("route") == "confluence"
        and "recent" in state["message"].casefold()
        and "page" in state["message"].casefold()
    ):
        return {"sources": [], "passages": []}
    chunks = KnowledgeRetriever().search(state["message"])
    return {
        "sources": [chunk.citation for chunk in chunks],
        "passages": [chunk.content for chunk in chunks],
    }


def _clean_passage(passage: str) -> str:
    cleaned = passage.strip()
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("```text", "").replace("```", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _summarize_passage(passage: str) -> str:
    cleaned = _clean_passage(passage)
    summary = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    return summary.strip()


def route_agent(state: SupervisorState) -> SupervisorState:
    route = state.get("route", "assistant")
    agent_map = {
        "assistant": AssistantAgent(),
        "chat": ChatAgent(),
        "email": EmailAgent(),
        "meeting": MeetingAgent(),
        "jira_confluence": JiraConfluenceAgent(),
        "confluence": JiraConfluenceAgent(),
        "document": DocumentAgent(),
    }

    agent = agent_map.get(route, AssistantAgent())
    response = agent.run(
        type(
            "Context",
            (),
            {
                "session_id": state.get("session_id", ""),
                "message": state.get("message", ""),
                "agent": route,
                "retrieved_sources": state.get("sources", []),
                "retrieved_chunks": state.get("passages", []),
            },
        )()
    )

    if route == "document" and not state.get("passages"):
        response = "No approved policy guidance matched. Add approved documents to data/knowledge_base."
    elif route == "document" and state.get("passages"):
        citations = state.get("sources", [])
        citation = citations[0] if citations else ""
        primary_passages = [
            _clean_passage(passage)
            for source, passage in zip(citations, state["passages"])
            if source == citation
        ]
        if not primary_passages:
            primary_passages = [_clean_passage(state["passages"][0])]
        response = "Approved policy guidance:\n" + "\n\n".join(primary_passages[:2])

    return {
        "agent_name": agent.name,
        "response": response,
    }


def synthesize_response(state: SupervisorState) -> SupervisorState:
    passages = state.get("passages", [])
    if passages:
        answer = passages[0].strip()
    else:
        answer = "No approved source matched. Add approved documents to data/knowledge_base."

    return {"response": answer}


def build_graph():
    graph = StateGraph(SupervisorState)
    graph.add_node("classify", classify_request)
    graph.add_node("retrieve", retrieve_knowledge)
    graph.add_node("route", route_agent)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "route")
    graph.add_edge("route", END)
    return graph.compile()


class Supervisor:
    def __init__(self) -> None:
        self.graph = build_graph()

    def handle(self, session_id: str, message: str, agent: str | None = None) -> str:
        result = self.graph.invoke({"session_id": session_id, "message": message, "agent": agent})
        return result.get("response", "")

    def handle_with_metadata(self, session_id: str, message: str, agent: str | None = None) -> dict[str, str]:
        result = self.graph.invoke({"session_id": session_id, "message": message, "agent": agent})
        return {
            "route": result.get("agent_name", "assistant"),
            "response": result.get("response", ""),
        }


supervisor = Supervisor()
