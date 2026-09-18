from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import settings
from backend.knowledge.loaders import ingest_confluence_page
from backend.knowledge.retriever import KnowledgeRetriever


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a Confluence page into the local knowledge base.")
    parser.add_argument("--url", required=True, help="Confluence page URL to fetch and ingest")
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=REPO_ROOT / "data" / "knowledge_base",
        help="Folder where the ingested markdown page should be stored",
    )
    parser.add_argument("--base-url", default=settings.confluence_base_url or settings.jira_base_url, help="Confluence site base URL")
    parser.add_argument("--email", default=settings.jira_email, help="Atlassian user email with Confluence access")
    parser.add_argument("--token", default=settings.jira_api_token, help="Atlassian API token")
    args = parser.parse_args()

    document_path = ingest_confluence_page(
        args.url,
        knowledge_root=args.knowledge_root,
        base_url=args.base_url,
        email=args.email,
        api_token=args.token,
    )
    retriever = KnowledgeRetriever(args.knowledge_root)
    retriever.rebuild_store()
    print(f"Imported Confluence page as {document_path}")
    print(f"Indexed {len(retriever.chunks)} chunks into {retriever.chunk_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
