from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.knowledge.retriever import KnowledgeRetriever


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the local RAG chunk store from the knowledge base.")
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=REPO_ROOT / "data" / "knowledge_base",
        help="Path to the knowledge base root to ingest.",
    )
    args = parser.parse_args()

    root = args.knowledge_root.resolve()
    retriever = KnowledgeRetriever(root)
    chunks = retriever.rebuild_store()

    print(f"Indexed {len(chunks)} chunks from {root}")
    print(f"Chunk store written to {retriever.chunk_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
