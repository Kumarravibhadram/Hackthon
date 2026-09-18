"""Business and process interpretation agent."""

from backend.agents.base import Agent
from backend.core.models import AgentContext


class FunctionalAgent(Agent):
    name = "functional"

    def run(self, context: AgentContext) -> str:
        prompt = context.message.strip() or "your request"
        return (
            "functional agent framed the business process implications for: "
            f"\"{prompt}\"."
        )
