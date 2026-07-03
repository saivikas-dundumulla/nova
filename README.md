# Nova — Enterprise AI Ombuds Assistant

Internal AI assistant that helps resolve operational issues through two role-gated workflows:

- **End User self-service** — an employee describes an issue in natural language, the agent searches an Azure AI Search index (ServiceNow incidents + Confluence KBs) and, if the issue is technical, Kibana logs. If it can't resolve the issue, it drafts a structured incident for the user to file.
- **Ombudsman-assisted investigation** — an ombudsman provides an existing incident number; the agent pulls that incident, finds related KBs, correlates Kibana logs, and produces an investigation summary.

Both flows run on the same LangGraph agent behind a FastAPI SSE endpoint. The Streamlit UI consumes the stream and renders token-by-token output and tool-call status live.

## Architecture

```
Streamlit UI  ──SSE──▶  FastAPI /chat/stream  ──▶  LangGraph  ─┬──▶ azure_search_retrieval  (Azure AI Search)
                                                               └──▶ kibana_search           (Kibana REST)
```

The Azure AI Search index is kept in sync with ServiceNow and Confluence by a separate upstream MCP pipeline — **out of scope for this app**. This app only reads from the index. The only new external integration built here is the Kibana REST client.

## Quick start

Requires Python 3.11+.

```bash
# 1. install
python -m pip install -e ".[dev]"

# 2. copy env template and fill in secrets
cp .env.example .env       # PowerShell: Copy-Item .env.example .env

# 3. in one terminal, start the API
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000

# 4. in another terminal, start the UI
streamlit run app/ui/streamlit_app.py
```

Open http://localhost:8501 and log in with one of the demo users (see `.env.example`).

### Demo credentials

The `.env.example` ships with two demo users, each with a password matching their username:
- `enduser1` / `enduser1` — End User role
- `ombuds1` / `ombuds1` — Ombudsman role

Generate a new bcrypt hash with:
```bash
python -c "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"
```

## Environment variables

See `.env.example` for the full list. Key groups:

| Group | Purpose |
|---|---|
| `AZURE_OPENAI_*` | LLM (Azure OpenAI, via `langchain-openai.AzureChatOpenAI`) |
| `AZURE_SEARCH_*` | Unified retrieval index — endpoint, key, index name, field mapping |
| `KIBANA_*` | Kibana REST endpoint + API key |
| `SESSION_JWT_*` | Stub-auth session token signing |
| `AUTH_USERS_JSON` | Stub-auth user store (JSON dict, bcrypt hashes) |
| `AUDIT_LOG_*` | JSONL audit log file settings |

## Testing

```bash
pytest -q
ruff check app tests
mypy app
```

## Repo layout

```
app/
├── config/     Settings + logging config
├── auth/       User model + Authenticator Protocol + stub impl
├── audit/      JSONL audit sink + event models
├── tools/      Azure Search + Kibana LangChain tools
├── graph/      LangGraph state + nodes + builder
├── api/        FastAPI app + SSE chat endpoint
└── ui/         Streamlit frontend
tests/
├── unit/       Unit tests per module
└── integration/  End-to-end SSE + graph flow tests
```

## Open items (see plan file)

- Azure AI Search index schema — placeholder field names in `.env.example`, swap to real ones.
- Kibana specifics — API key auth assumed; confirm index pattern.
- Escalation draft schema — v1 fields are title/category/description/evidence.
- Audit retention policy — local rotating file for v1.
- Real auth — Entra ID OIDC drops in behind the `Authenticator` Protocol.

## Non-functional properties

- **Streaming** — end-to-end token + tool-event streaming via `graph.astream_events(v="v2")` → SSE.
- **Graceful degradation** — if Kibana or Azure Search is down, the agent proceeds with a caveat rather than failing the request.
- **Audit** — every tool call is emitted to a separate JSONL log with hashed queries, never raw content.
- **PII** — free-text user queries and incident bodies are never written to the app-level log; audit log stores only sha256 hashes.
