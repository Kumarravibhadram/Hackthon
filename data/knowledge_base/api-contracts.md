# API Contracts

Approved workspace endpoints:

- `POST /api/v1/chat/sessions` - create a workspace session
- `POST /api/v1/chat/sessions/{session_id}/messages` - submit an employee request
- `GET /api/v1/chat/sessions/{session_id}` - retrieve conversation state
- `GET /api/v1/dashboard/summary` - retrieve dashboard metrics
- `POST /api/v1/knowledge/search` - search approved knowledge sources

Keep request and response models in `backend/app/api/schemas/` so the frontend does not depend on internal agent implementations.
