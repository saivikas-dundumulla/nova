from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from passlib.hash import bcrypt

# --- Set required env before app modules import Settings -------------------

TEST_JWT_SECRET = "test-secret-key-do-not-use-in-production-please"
TEST_PASSWORD = "test-pass"
_ENDUSER_HASH = bcrypt.hash(TEST_PASSWORD)
_OMBUDS_HASH = bcrypt.hash(TEST_PASSWORD)

os.environ.setdefault("SESSION_JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("SESSION_JWT_ALG", "HS256")
os.environ.setdefault(
    "AUTH_USERS_JSON",
    json.dumps(
        {
            "enduser1": {"password_hash": _ENDUSER_HASH, "role": "enduser", "email": "e@x.io"},
            "ombuds1": {"password_hash": _OMBUDS_HASH, "role": "ombuds", "email": "o@x.io"},
        }
    ),
)
# Point the KB client at a fake endpoint; tests inject a mock transport/client.
os.environ.setdefault("AZURE_SEARCH_ENDPOINT", "https://fake.search.windows.net")
os.environ.setdefault("AZURE_SEARCH_API_KEY", "fake-key")
os.environ.setdefault("AZURE_SEARCH_KNOWLEDGE_BASE", "nova-kb")
os.environ.setdefault("AZURE_SEARCH_API_VERSION", "2026-05-01-preview")


@pytest.fixture(autouse=True)
def _isolate_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point audit log at a temp file per test; clear cached Settings and audit logger."""
    log_file = tmp_path / "audit.log"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(log_file))

    from app.config import settings as settings_mod
    settings_mod.get_settings.cache_clear()

    import logging
    audit = logging.getLogger("audit")
    for h in list(audit.handlers):
        audit.removeHandler(h)

    from app.audit import logger as audit_mod
    audit_mod._singleton = None

    from app.config.logging_config import setup_logging
    setup_logging()

    yield log_file


@pytest.fixture
def fake_kb_response() -> dict:
    """A representative knowledge base `retrieve` response (answer synthesis mode)."""
    return {
        "@odata.context": "https://fake.search.windows.net/$metadata#...AgentRetrievalResponse",
        "response": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "To reset your VPN password, open Settings → Security → "
                        "Reset. This resolves most connection errors.",
                    }
                ],
            }
        ],
        "activity": [
            {"type": "modelQueryPlanning", "id": 0, "inputTokens": 100, "outputTokens": 20},
            {"type": "mcpServer", "id": 1, "knowledgeSourceName": "nova-confluence-ks-ext", "count": 3},
            {"type": "modelAnswerSynthesis", "id": 2, "inputTokens": 500, "outputTokens": 40},
        ],
        "references": [
            {
                "type": "mcpServer",
                "id": "0",
                "activitySource": 1,
                "docKey": "vpn-reset",
                "sourceData": {"title": "Reset your VPN password", "url": "https://kb/vpn-reset"},
            }
        ],
    }
