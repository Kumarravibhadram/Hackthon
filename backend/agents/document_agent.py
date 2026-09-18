"""Document analysis agent."""

from backend.agents.base import Agent
from backend.core.models import AgentContext


class DocumentAgent(Agent):
    name = "document"

    def run(self, context: AgentContext) -> str:
        prompt = context.message.strip() or "your request"
        return (
            f"Reviewed policy guidance for \"{prompt}\"."
        )
