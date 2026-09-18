"""Approved knowledge search endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.knowledge.retriever import KnowledgeRetriever

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/search")
def search_knowledge(request: KnowledgeSearchRequest) -> dict[str, object]:
    chunks = KnowledgeRetriever().search(request.query, top_k=request.top_k)
    return {
        "query": request.query,
        "results": [
            {
                "citation": chunk.citation,
                "source": chunk.source,
                "content": chunk.content,
                "score": chunk.score,
                "page": chunk.page,
            }
            for chunk in chunks
        ],
    }
