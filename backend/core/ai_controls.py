"""Shared LLM guardrails and optional LangSmith tracking."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from backend.app.config import settings

_MAX_INPUT_CHARS = 12_000
_MAX_OUTPUT_CHARS = 20_000
_BLOCKED_INPUT_PATTERNS = (
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"reveal\s+(?:the\s+)?system\s+prompt",
    r"show\s+(?:the\s+)?hidden\s+instructions",
    r"developer\s+message",
)
_SECRET_PATTERNS = (
    r"\bsk-[A-Za-z0-9_-]{20,}\b",
    r"\b(?:ATATT|lsv2_)[A-Za-z0-9_-]{12,}\b",
)


def guard_input(value: str) -> str:
    """Validate user-controlled text before sending it to an LLM."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("LLM input cannot be empty")
    if len(normalized) > _MAX_INPUT_CHARS:
        raise ValueError(f"LLM input exceeds the {_MAX_INPUT_CHARS}-character limit")
    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in _BLOCKED_INPUT_PATTERNS):
        raise ValueError("The request contains a blocked instruction pattern")
    return normalized


def guard_output(value: str) -> str:
    """Limit model output and redact common credential formats."""
    output = value.strip()[:_MAX_OUTPUT_CHARS]
    for pattern in _SECRET_PATTERNS:
        output = re.sub(pattern, "[REDACTED]", output)
    return output


def track_llm_run(name: str, *, provider: str, model: str, input_text: str, output_text: str) -> None:
    """Send minimal telemetry to LangSmith when explicitly enabled."""
    if not getattr(settings, "langsmith_tracing", False) or not getattr(settings, "langsmith_api_key", ""):
        return

    try:
        from langsmith import Client

        client = Client(
            api_url=getattr(settings, "langsmith_endpoint", "") or None,
            api_key=getattr(settings, "langsmith_api_key", ""),
        )
        content = settings.langsmith_trace_content
        run_id = uuid4()
        client.create_run(
            id=run_id,
            name=name,
            run_type="llm",
            inputs={"text": input_text if content else "[content redacted]"},
            serialized={"provider": provider, "model": model},
            project_name=getattr(settings, "langsmith_project", "bank-employee-ai"),
        )
        client.update_run(
            run_id,
            outputs={"text": output_text if content else "[content redacted]"},
        )
    except Exception:
        # Observability must never break a user request.
        return
