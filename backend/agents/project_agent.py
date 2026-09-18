"""Project planning and delivery interpretation agent."""

from backend.agents.base import Agent
from backend.core.models import AgentContext


class ProjectAgent(Agent):
    name = "project"

    def run(self, context: AgentContext) -> str:
        prompt = context.message.strip() or "your request"
        return (
            "project agent mapped the request to project delivery and planning work for: "
            f"\"{prompt}\"."
        )
