"""Hybrid knowledge retrieval with Azure AI Search and a local fallback."""

from collections import Counter
import json
from pathlib import Path
import re
from typing import Protocol

import httpx

from backend.app.config import settings
from backend.core.models import RetrievedChunk
from backend.knowledge.loaders import DocumentChunk, load_chunks


class PgVectorChunkStore:
    def __init__(self, table_name: str | None = None) -> None:
        self.database_url = settings.database_url
        self.table_name = table_name or settings.vector_table

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required for pgvector storage") from exc
        return psycopg.connect(self.database_url)

    def ensure_schema(self) -> None:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for pgvector storage")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        chunk_id text PRIMARY KEY,
                        source text NOT NULL,
                        content text NOT NULL,
                        page integer,
                        embedding vector({settings.openai_embedding_dimension})
                    )
                    """
                )

    def write_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if not self.database_url:
            return
        if len(chunks) != len(embeddings):
            raise ValueError("Each document chunk must have one embedding")
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                for chunk, embedding in zip(chunks, embeddings):
                    cur.execute(
                        f"""
                        INSERT INTO {self.table_name} (chunk_id, source, content, page, embedding)
                        VALUES (%s, %s, %s, %s, %s::vector)
                        ON CONFLICT (chunk_id)
                        DO UPDATE SET source = EXCLUDED.source, content = EXCLUDED.content, page = EXCLUDED.page
                        """,
                        (
                            chunk.chunk_id,
                            chunk.source,
                            chunk.content,
                            chunk.page,
                            "[" + ",".join(str(value) for value in embedding) + "]",
                        ),
                    )

    def has_embeddings(self) -> bool:
        if not self.database_url:
            return False
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT EXISTS (SELECT 1 FROM {self.table_name} WHERE embedding IS NULL)"
                )
                has_missing = cur.fetchone()[0]
        return not has_missing

    def read_chunks(self) -> list[DocumentChunk]:
        if not self.database_url:
            return []
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT chunk_id, source, content, page FROM {self.table_name} ORDER BY source, page"
                )
                rows = cur.fetchall()
        return [
            DocumentChunk(chunk_id=row[0], source=row[1], content=row[2], page=row[3])
            for row in rows
        ]

    def search(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        if not self.database_url:
            return []
        self.ensure_schema()
        vector = "[" + ",".join(str(value) for value in embedding) + "]"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT chunk_id, source, content, page,
                           1 - (embedding <=> %s::vector) AS score
                    FROM {self.table_name}
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vector, vector, top_k),
                )
                rows = cur.fetchall()
        return [
            RetrievedChunk(
                chunk_id=row[0],
                source=row[1],
                content=row[2],
                score=float(row[4]),
                page=row[3],
            )
            for row in rows
        ]


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    """Embedding client for OpenAI and OpenAI-compatible providers."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for embeddings")
        self.endpoint = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = settings.openai_embedding_model

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            f"{self.endpoint}/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": self.model, "input": text},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return [float(value) for value in payload["data"][0]["embedding"]]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = httpx.post(
            f"{self.endpoint}/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        items = sorted(response.json()["data"], key=lambda item: item["index"])
        return [[float(value) for value in item["embedding"]] for item in items]


class ChromaFaissVectorStore:
    """Persist embeddings in ChromaDB and search them with FAISS on CPU."""

    def __init__(self) -> None:
        try:
            import chromadb
            import faiss
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("chromadb, faiss-cpu, and numpy are required for vector storage") from exc

        self._faiss = faiss
        self._numpy = np
        client = chromadb.PersistentClient(path=str(Path(settings.vector_store_path).resolve()))
        self.collection = client.get_or_create_collection(
            name=settings.vector_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def read_chunks(self) -> list[DocumentChunk]:
        data = self.collection.get(include=["documents", "metadatas"])
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []
        ids = data.get("ids") or []
        return [
            DocumentChunk(
                chunk_id=chunk_id,
                source=str(metadata.get("source", "unknown")),
                content=document,
                page=metadata.get("page"),
            )
            for chunk_id, document, metadata in zip(ids, documents, metadatas)
        ]

    def has_embeddings(self) -> bool:
        return self.collection.count() > 0

    def write_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Each document chunk must have one embedding")

        existing_ids = self.collection.get(include=[]).get("ids") or []
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        self.collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            embeddings=embeddings,
            metadatas=[
                {"source": chunk.source, "page": chunk.page if chunk.page is not None else -1}
                for chunk in chunks
            ],
        )

    def search(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        data = self.collection.get(include=["embeddings", "documents", "metadatas"])
        ids = data.get("ids") or []
        embeddings = data.get("embeddings")
        if not ids or embeddings is None or len(embeddings) == 0:
            return []

        vectors = self._numpy.asarray(embeddings, dtype="float32")
        query = self._numpy.asarray([embedding], dtype="float32")
        self._faiss.normalize_L2(vectors)
        self._faiss.normalize_L2(query)
        index = self._faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        scores, positions = index.search(query, min(top_k, len(ids)))
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []
        results: list[RetrievedChunk] = []
        for score, position in zip(scores[0], positions[0]):
            if position < 0:
                continue
            metadata = metadatas[position] or {}
            page = metadata.get("page")
            results.append(
                RetrievedChunk(
                    chunk_id=ids[position],
                    source=str(metadata.get("source", "unknown")),
                    content=documents[position],
                    score=float(score),
                    page=None if page in (None, -1) else int(page),
                )
            )
        return results


class AzureSearchClient:
    """Azure adapter; local development does not require cloud credentials."""

    def __init__(self, endpoint: str, index_name: str) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        if not settings.azure_search_key:
            raise ValueError("AZURE_SEARCH_KEY is required for Azure AI Search")
        self.client = SearchClient(endpoint, index_name, AzureKeyCredential(settings.azure_search_key))

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        results = self.client.search(search_text=query, top=top_k, query_type="semantic")
        return [
            RetrievedChunk(
                chunk_id=str(item.get("id", "")),
                source=str(item.get("source", "unknown")),
                content=str(item.get("content", "")),
                score=float(item.get("@search.reranker_score", item.get("@search.score", 0))),
                page=item.get("page"),
            )
            for item in results
        ]


class LocalReranker:
    def rerank(self, query: str, chunks: list[tuple[float, DocumentChunk]]) -> list[tuple[float, DocumentChunk]]:
        query_terms = set(_terms(query))
        if not query_terms:
            return chunks

        reranked: list[tuple[float, DocumentChunk]] = []
        for score, chunk in chunks:
            source_terms = set(_terms(chunk.source))
            content_terms = set(_terms(chunk.content))
            overlap = len(query_terms & content_terms)
            source_overlap = len(query_terms & source_terms)
            title_bonus = 0.25 * source_overlap
            content_bonus = 0.1 * overlap
            reranked.append((score + title_bonus + content_bonus, chunk))

        reranked.sort(key=lambda item: item[0], reverse=True)
        return reranked


class LocalLexicalRetriever:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = chunks
        self.reranker = LocalReranker()

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        query_terms = Counter(_terms(query))
        if not query_terms:
            return []

        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in self.chunks:
            terms = Counter(_terms(chunk.content))
            matched_terms = query_terms.keys() & terms.keys()
            if not matched_terms:
                continue
            if len(query_terms) > 1 and len(matched_terms) < 2:
                continue

            overlap = sum(min(query_terms[term], terms[term]) for term in query_terms)

            unique_query_terms = len(query_terms)
            unique_chunk_terms = len(terms)
            weighted_overlap = overlap * 10
            term_coverage = overlap / unique_query_terms
            chunk_density = term_coverage * (len(terms) / max(unique_chunk_terms, 1))
            score = weighted_overlap + term_coverage + chunk_density
            scored.append((score, chunk))

        reranked = self.reranker.rerank(query, scored)
        return [
            RetrievedChunk(chunk.chunk_id, chunk.source, chunk.content, score, chunk.page)
            for score, chunk in reranked[:top_k]
        ]


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "for", "from", "how", "i", "in",
    "is", "it", "me", "of", "on", "or", "that", "the", "this", "to", "what", "with",
    "you", "your",
}


def _terms(text: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]{2,}", text.lower()) if term not in _STOP_WORDS]


class KnowledgeRetriever:
    def __init__(self, knowledge_root: Path | None = None, search_client: AzureSearchClient | None = None) -> None:
        root = knowledge_root or Path("data/knowledge_base")
        self.knowledge_root = root
        self.search_client = search_client
        if self.search_client is None and settings.azure_search_endpoint and settings.azure_search_index:
            self.search_client = AzureSearchClient(settings.azure_search_endpoint, settings.azure_search_index)
        self.chunk_store_path = (root / ".vector_store" / "chunks.json").resolve()
        self.vector_store: ChromaFaissVectorStore | None = None
        if settings.vector_store_backend.lower() in {"chroma", "chromadb", "faiss"}:
            try:
                self.vector_store = ChromaFaissVectorStore()
            except RuntimeError:
                self.vector_store = None
        self.pg_store = (
            PgVectorChunkStore()
            if settings.vector_store_backend.lower() == "pgvector" and settings.database_url
            else None
        )
        self.embedding_provider: OpenAIEmbeddingProvider | None = None
        if (self.pg_store is not None or self.vector_store is not None) and settings.openai_api_key:
            self.embedding_provider = OpenAIEmbeddingProvider()
        elif self.pg_store is not None:
            self.pg_store = None
        elif self.vector_store is not None:
            self.vector_store = None
        self.chunks = self._load_or_rebuild_chunks(root)
        self.local = LocalLexicalRetriever(self.chunks)

    def _load_or_rebuild_chunks(self, root: Path) -> list[DocumentChunk]:
        if self.vector_store is not None:
            try:
                chunks = self.vector_store.read_chunks()
                if chunks and (self.embedding_provider is None or self.vector_store.has_embeddings()):
                    return chunks
            except Exception:
                self.vector_store = None

        if self.pg_store is not None:
            try:
                chunks = self.pg_store.read_chunks()
                if chunks and (self.embedding_provider is None or self.pg_store.has_embeddings()):
                    return chunks
            except Exception:
                self.pg_store = None

        if self.chunk_store_path.exists():
            data = json.loads(self.chunk_store_path.read_text(encoding="utf-8"))
            if data:
                return [
                    DocumentChunk(
                        chunk_id=item["chunk_id"],
                        source=item["source"],
                        content=item["content"],
                        page=item.get("page"),
                    )
                    for item in data
                ]

        chunks = load_chunks(root)
        self._write_chunks(chunks)
        return chunks

    def _write_chunks(self, chunks: list[DocumentChunk]) -> None:
        if self.vector_store is not None:
            if self.embedding_provider is None:
                raise RuntimeError("OPENAI_API_KEY is required to write ChromaDB embeddings")
            embeddings = self.embedding_provider.embed_many([chunk.content for chunk in chunks])
            self.vector_store.write_chunks(chunks, embeddings)
            return

        if self.pg_store is not None:
            if self.embedding_provider is None:
                raise RuntimeError("OPENAI_API_KEY is required to write pgvector embeddings")
            embeddings = self.embedding_provider.embed_many([chunk.content for chunk in chunks])
            self.pg_store.write_chunks(chunks, embeddings)
            return

        self.chunk_store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "content": chunk.content,
                "page": chunk.page,
            }
            for chunk in chunks
        ]
        self.chunk_store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def rebuild_store(self) -> list[DocumentChunk]:
        chunks = load_chunks(self.knowledge_root)
        self.chunks = chunks
        self.local = LocalLexicalRetriever(chunks)
        self._write_chunks(chunks)
        return chunks

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        if self.vector_store is not None and self.embedding_provider is not None:
            try:
                return self.vector_store.search(self.embedding_provider.embed(query), top_k)
            except Exception:
                pass
        if self.pg_store is not None and self.embedding_provider is not None:
            try:
                return self.pg_store.search(self.embedding_provider.embed(query), top_k)
            except Exception:
                pass
        if self.search_client is not None:
            return self.search_client.search(query, top_k)
        return self.local.search(query, top_k)
