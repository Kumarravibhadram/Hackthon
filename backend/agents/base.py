"""Base contract shared by all agents."""

from abc import ABC, abstractmethod

from backend.core.models import AgentContext


class Agent(ABC):
    name: str

    @abstractmethod
    def run(self, context: AgentContext) -> str:
        raise NotImplementedError
