"""Knowledge retrieval and citation agent."""

from backend.agents.base import Agent
from backend.core.models import AgentContext
from backend.knowledge.retriever import KnowledgeRetriever


class KnowledgeRagAgent(Agent):
    name = "knowledge_rag"

    def __init__(self, retriever: KnowledgeRetriever | None = None) -> None:
        self.retriever = retriever or KnowledgeRetriever()

    def run(self, context: AgentContext) -> str:
        context.retrieved_chunks = self.retriever.search(context.message)
        context.retrieved_sources = [chunk.citation for chunk in context.retrieved_chunks]
        if not context.retrieved_chunks:
            return "No approved knowledge source matched the request."
        return "\n".join(f"{chunk.citation} {chunk.content}" for chunk in context.retrieved_chunks)
