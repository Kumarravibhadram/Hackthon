"""Technical implementation interpretation agent."""

from backend.agents.base import Agent
from backend.core.models import AgentContext


class TechnicalAgent(Agent):
    name = "technical"

    def run(self, context: AgentContext) -> str:
        prompt = context.message.strip() or "your request"
        return (
            "technical agent translated the request into implementation guidance for: "
            f"\"{prompt}\"."
        )
