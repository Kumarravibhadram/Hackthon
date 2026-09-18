# Architecture

```text
Bank employee
    |
    v
Frontend workspace (chat + dashboard)
    |
    v
API layer -> Supervisor / orchestrator
                 |
                 +-> Email agent
                 +-> Chat agent
                 +-> Document agent
                            |
                            v
                       Knowledge / RAG agent
                       /        |        \
              Functional   Technical   Project agents
                       \        |        /
                            v
                       Synthesis agent
                            |
                            v
                 Functional + technical + executive views
```

## Responsibilities

- **Supervisor**: classifies intent, selects agents, manages state, and handles failures.
- **Specialist agents**: perform email, chat, and document workflows.
- **Knowledge/RAG agent**: retrieves approved sources and returns citation-backed answers.
- **Domain agents**: frame retrieved information for functional, technical, or project needs.
- **Synthesis agent**: combines results into role-appropriate views.
- **API layer**: exposes stable contracts to the frontend and authentication boundary.
