"""Document upload and deterministic analysis services."""

from collections import Counter
from pathlib import Path
import re
from typing import Any

from backend.knowledge.loaders import SUPPORTED_SUFFIXES, load_text


def analyze_document(filename: str, text: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text).strip()
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    action_terms = ("must", "should", "need to", "required", "review", "complete", "submit", "send", "approve", "owner")
    actions = [sentence for sentence in sentences if any(term in sentence.lower() for term in action_terms)][:8]
    headings = re.findall(r"(?:^|\n)\s*(?:#{1,6}\s*)?([A-Z][A-Za-z0-9 /&_-]{3,60})\s*(?::|$)", text, re.MULTILINE)
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]+", normalized.lower())
    keywords = [word for word, _ in Counter(words).most_common(10) if len(word) > 3]

    summary_sentences = []
    for sentence in sentences:
        if len(" ".join(summary_sentences + [sentence]).split()) > 250:
            break
        summary_sentences.append(sentence)

    summary = " ".join(summary_sentences).strip() or "No readable text was found."

    return {
        "filename": filename,
        "characters": len(text),
        "word_count": len(words),
        "summary": summary,
        "headings": list(dict.fromkeys(headings))[:12],
        "action_items": actions,
        "keywords": keywords,
        "text": text,
    }


def validate_filename(filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported document type. Supported types: {supported}")