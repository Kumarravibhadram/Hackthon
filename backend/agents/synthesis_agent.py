"""Combine specialist outputs into audience-specific views."""

from backend.agents.base import Agent
from backend.core.models import AgentContext, SynthesisResult


class SynthesisAgent(Agent):
    name = "synthesis"

    def run(self, context: AgentContext) -> str:
        synthesis = self.synthesize(context)
        parts = [
            f"Functional view: {synthesis.functional_view or 'No functional view available.'}",
            f"Technical view: {synthesis.technical_view or 'No technical view available.'}",
            f"Executive view: {synthesis.executive_view or 'No executive view available.'}",
        ]
        return "\n".join(parts)

    def synthesize(self, context: AgentContext) -> SynthesisResult:
        return SynthesisResult(
            functional_view=context.agent_outputs.get("functional", ""),
            technical_view=context.agent_outputs.get("technical", ""),
            executive_view=context.agent_outputs.get("project", ""),
        )
