# Nova — Enterprise AI Ombuds Assistant

Internal AI assistant that helps resolve operational issues through two role-gated workflows:

- **End User self-service** — an employee describes an issue in natural language and gets a grounded resolution.
- **Ombudsman-assisted investigation** — an ombudsman provides an incident number and gets an investigation summary.

Both flows send the user's prompt to a single **Azure AI Search agentic knowledge base**, which performs retrieval over its MCP knowledge sources (ServiceNow + Confluence) **and** answer synthesis in-service, then returns a finished, grounded answer with citations. The app itself holds **no LLM** and connects to **only** Azure AI Search.

## Architecture

```
Streamlit UI  ──SSE──▶  FastAPI /chat/stream  ──HTTPS──▶  Azure AI Search
                                                          knowledgebases/{kb}/retrieve
                                                          (retrieval + LLM synthesis in-service,
                                                           over ServiceNow + Confluence MCP sources)
```

- **No separate LLM.** The knowledge base (`nova-kb`) has its own model configured; the backend just posts the prompt and receives the synthesized answer.
- **One external dependency.** The only outbound connection is to the Azure AI Search endpoint.
- The retrieve API returns the whole answer at once; the backend chunks it into SSE `token` frames so the UI still renders a live typing effect.

## Quick start

Requires Python 3.11+.

```bash
# 1. install
python -m pip install -e ".[dev]"

# 2. copy env template and fill in secrets
cp .env.example .env       # PowerShell: Copy-Item .env.example .env

# 3. in one terminal, start the API
python -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000

# 4. in another terminal, start the UI
python -m streamlit run app/ui/streamlit_app.py
```

Open http://localhost:8501 and log in with a demo user.

> Note: `uvicorn` / `streamlit` may not be on your PATH after `pip install`. Use `python -m uvicorn …` / `python -m streamlit …` as shown.

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
| `AZURE_SEARCH_*` | Knowledge base endpoint, API key, API version, and KB name (`nova-kb`) |
| `SESSION_JWT_*` | Stub-auth session token signing |
| `AUTH_USERS_JSON` | Stub-auth user store (JSON dict, bcrypt hashes) |
| `AUDIT_LOG_*` | JSONL audit log file settings |

The retrieve endpoint used is:
`POST {AZURE_SEARCH_ENDPOINT}/knowledgebases/{AZURE_SEARCH_KNOWLEDGE_BASE}/retrieve?api-version={AZURE_SEARCH_API_VERSION}`

## Testing

```bash
python -m pytest -q
python -m ruff check app tests
```

## Repo layout

```
app/
├── config/     Settings + logging config
├── auth/       User model + Authenticator Protocol + stub impl
├── audit/      JSONL audit sink + event models
├── tools/      Knowledge base client (Azure AI Search retrieve) + schemas
├── api/        FastAPI app + SSE chat endpoint
└── ui/         Streamlit frontend (views/ holds login + role screens; not a Streamlit pages/ dir on purpose)
tests/
├── unit/       Auth, audit, KB client, SSE parser
└── integration/  Auth API + /chat/stream SSE
```

## Non-functional properties

- **Streaming** — status events + chunked answer streamed to the UI via SSE.
- **Graceful degradation** — if the knowledge base is unreachable or returns `206 Partial Content`, the UI shows a source-status banner instead of failing.
- **Audit** — every retrieve call is emitted to a separate JSONL log with a hashed query, never raw content.
- **PII** — user prompts and answer bodies are never written to the app-level log; the audit log stores only a sha256 hash of the query.

## Notes / open items

- **API version:** the working data-plane version on this service is `2026-05-01-preview` against the `/knowledgebases/{name}/retrieve` route. (The older `/agents/` route only supports up to `2025-08-01-preview` and rejects the agents' newer features.)
- **Auth:** stubbed for v1 behind the `Authenticator` Protocol in `app/auth/base.py`; Entra ID / OIDC drops in there without touching the rest of the app.
- **Multi-turn:** the UI sends prior turns as `history`, which the backend forwards to the knowledge base for conversational context.
