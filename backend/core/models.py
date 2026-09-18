"""Shared domain models passed between agents."""

from dataclasses import dataclass, field


@dataclass
class AgentContext:
    session_id: str
    message: str
    agent: str | None = None
    retrieved_sources: list[str] = field(default_factory=list)
    retrieved_chunks: list["RetrievedChunk"] = field(default_factory=list)
    agent_outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class SynthesisResult:
    functional_view: str
    technical_view: str
    executive_view: str


@dataclass(frozen=True)
class RetrievedChunk:
    """A grounded passage returned by the knowledge layer."""

    chunk_id: str
    source: str
    content: str
    score: float
    page: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        location = f", page {self.page}" if self.page is not None else ""
        return f"[{self.source}{location}]"
