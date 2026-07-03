from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://fake.openai.azure.com/")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "fake")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
os.environ.setdefault("AZURE_SEARCH_ENDPOINT", "https://fake.search.windows.net")
os.environ.setdefault("AZURE_SEARCH_API_KEY", "fake")
os.environ.setdefault("AZURE_SEARCH_INDEX_NAME", "test-index")
os.environ.setdefault("KIBANA_URL", "https://kibana.example.com")
os.environ.setdefault("KIBANA_API_KEY", "fake")


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
def fake_search_hits() -> list[dict[str, Any]]:
    return [
        {
            "id": "1",
            "source_type": "confluence",
            "title": "Reset your VPN password",
            "content": "Open Settings → Security → Reset. This resolves 90% of connection errors.",
            "url": "https://kb.example.com/vpn-reset",
            "score": 0.91,
        },
        {
            "id": "2",
            "source_type": "servicenow",
            "incident_number": "INC0012345",
            "title": "VPN outage in region EU-West",
            "content": "Full outage 2024-05-01 08:00–10:30 UTC. Root cause: expired certificate.",
            "url": "https://sn.example.com/INC0012345",
            "score": 0.87,
        },
    ]


@pytest.fixture
def fake_log_hits() -> list[dict[str, Any]]:
    return [
        {
            "ts": "2026-07-03T09:15:22Z",
            "service": "vpn-gateway",
            "level": "ERROR",
            "message": "TLS handshake failed: certificate expired",
        }
    ]
