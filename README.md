# Bank Employee AI Workspace

A multi-agent workspace for bank employees. The system routes requests through an AI supervisor to specialist agents, retrieves trusted knowledge, and returns functional, technical, and executive views.

## Project layout

- `frontend/`: employee chat and dashboard UI
- `backend/`: API, supervisor, specialist agents, RAG, and synthesis
- `data/`: source documents and vector-index artifacts
- `tests/`: unit, integration, and end-to-end tests
- `docs/`: architecture and API notes

## Suggested next steps

1. Choose the backend framework and LLM provider.
2. Implement the supervisor contract in `backend/orchestrator/supervisor.py`.
3. Add agent implementations under `backend/agents/`.
4. Connect the frontend chat client to the backend API.
5. Add approved bank policies to `data/knowledge_base/`.

## Development

The scaffold is intentionally framework-neutral. Keep secrets in `.env` and use `.env.example` as the shared configuration contract.

## Run with Docker Compose

Copy `.env.example` to `.env`, then start the local services:

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Azure AI Search and Azure AI Foundry remain external services and are configured through `.env`.

### Embedding-backed RAG

The knowledge pipeline extracts and chunks approved documents, creates embeddings, stores them in
ChromaDB, embeds each incoming query, and ranks normalized vectors with FAISS CPU cosine similarity.
Configure these values
in `.env` before starting Docker Compose:

```env
VECTOR_STORE_BACKEND=chroma
VECTOR_STORE_PATH=data/vector_store
VECTOR_COLLECTION=banking_knowledge
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-api-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSION=1536
```

Rebuild the index after adding or changing approved documents:

```bash
python scripts/ingest.py
```

Without `OPENAI_API_KEY`, development falls back to the local JSON chunk store and lexical retrieval;
it does not claim to provide vector similarity search.

## Microsoft Graph calendar

New Outlook and Outlook Web calendar access uses Microsoft Graph rather than the Classic Outlook COM API.
Register a public-client application in Microsoft Entra ID, grant delegated `Calendars.ReadWrite` and
`User.Read` permissions, and add these values to `.env`:

```env
GRAPH_CLIENT_ID=your-public-client-id
GRAPH_TENANT_ID=common
GRAPH_SCOPES=Calendars.ReadWrite User.Read
GRAPH_TOKEN_CACHE_PATH=data/graph_token_cache.json
GRAPH_TIMEZONE=UTC
```

The first calendar request starts Microsoft device authentication and prints a one-time code in the backend
terminal. Complete that sign-in once; the MSAL token cache is reused for later calendar reads and writes.

## Microsoft Graph mail

MailMate uses Microsoft Graph as its primary mailbox integration. Register the same public-client Entra ID application
with delegated `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, and `User.Read` permissions, then configure:

```env
GRAPH_CLIENT_ID=your-public-client-id
GRAPH_TENANT_ID=common
GRAPH_MAIL_SCOPES=Mail.Read Mail.ReadWrite Mail.Send User.Read
MAIL_IMPORTANT_SENDERS=ceo@bank.example,manager@bank.example
```

The first mail request starts device authentication in the backend terminal. MailMate reads the current user's mailbox,
returns the latest email on request, and triages every message by read state, relevance, sender importance,
attachments, and action needed. Set `ALLOW_OUTLOOK_FALLBACK=false` to require Graph and disable local Outlook COM.
