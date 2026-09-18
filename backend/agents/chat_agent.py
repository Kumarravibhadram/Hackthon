"""Conversational chat agent."""

from backend.agents.base import Agent
from backend.core.models import AgentContext


class ChatAgent(Agent):
    name = "chat"

    def run(self, context: AgentContext) -> str:
        prompt = context.message.strip() or "your request"
        return (
            f"Handled the conversational workspace request for \"{prompt}\"."
        )
