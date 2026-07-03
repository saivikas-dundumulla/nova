from __future__ import annotations

import logging
import logging.handlers
import os
import re
from pathlib import Path
from typing import Any

import structlog

from app.config.settings import Settings, get_settings

_SENSITIVE_KEYS = {
    "user_query",
    "message",
    "password",
    "password_hash",
    "authorization",
    "api_key",
    "draft_incident",
    "body",
    "content",
}
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _EMAIL_RE.sub("<redacted-email>", value)
    return value


def _pii_scrubber(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: drop or mask sensitive keys before emit."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "<redacted>"
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def setup_logging(settings: Settings | None = None) -> None:
    """Configure the app logger (structlog+JSON) and the audit logger (JSONL)."""
    s = settings or get_settings()
    log_level = getattr(logging, s.log_level.upper(), logging.INFO)

    # Ensure audit log directory exists
    audit_path = Path(s.audit_log_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    # --- root / app logger (structlog) ---
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[logging.StreamHandler()],
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _pii_scrubber,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    # --- audit logger (isolated, JSONL, rotating) ---
    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    if not audit_logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            audit_path,
            maxBytes=s.audit_log_max_bytes,
            backupCount=s.audit_log_backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)


def get_app_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or "app")


def get_audit_logger() -> logging.Logger:
    return logging.getLogger("audit")


# Enable in tests to keep stdout quiet
if os.getenv("PYTEST_CURRENT_TEST"):  # pragma: no cover
    logging.getLogger().setLevel(logging.WARNING)
