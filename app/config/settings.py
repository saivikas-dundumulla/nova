from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthUser(BaseModel):
    password_hash: str
    role: str
    email: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_name: str = "nova-ombuds"
    app_env: str = "dev"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:8501"

    # Session / JWT
    session_jwt_secret: str = "change-me"
    session_jwt_alg: str = "HS256"
    session_ttl_minutes: int = 480

    # Auth (stub)
    auth_users_json: str = "{}"

    # Azure AI Search — agentic knowledge base (retrieval + synthesis handled by the service)
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_api_version: str = "2026-05-01-preview"
    # Knowledge base that unifies the ServiceNow + Confluence MCP sources.
    azure_search_knowledge_base: str = "nova-kb"
    # Optional per-role override; falls back to azure_search_knowledge_base when blank.
    azure_search_kb_enduser: str = ""
    azure_search_kb_ombuds: str = ""
    azure_search_timeout_seconds: float = 120.0
    azure_search_max_retries: int = 2

    # Conversation memory (per-user JSON store) + answer cache
    conversations_dir: str = "data/conversations"
    cache_enabled: bool = True
    # Question-similarity score (0..1) at/above which a past answer is reused instead of the KB.
    cache_similarity_threshold: float = 0.82
    # Ignore very short questions for cache matching (too ambiguous to reuse safely).
    cache_min_question_chars: int = 8

    # Audit / logging
    audit_log_path: str = "logs/audit.log"
    audit_log_max_bytes: int = 10 * 1024 * 1024
    audit_log_backup_count: int = 5
    log_level: str = "INFO"
    audit_hash_user_id: bool = False

    @field_validator("api_cors_origins")
    @classmethod
    def _strip_cors(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    def knowledge_base_for_role(self, role: str) -> str:
        if role == "enduser" and self.azure_search_kb_enduser:
            return self.azure_search_kb_enduser
        if role == "ombuds" and self.azure_search_kb_ombuds:
            return self.azure_search_kb_ombuds
        return self.azure_search_knowledge_base

    @property
    def auth_users(self) -> dict[str, AuthUser]:
        try:
            raw: dict[str, Any] = json.loads(self.auth_users_json) if self.auth_users_json else {}
        except json.JSONDecodeError as e:  # pragma: no cover — surfaces on startup
            raise ValueError(f"AUTH_USERS_JSON is not valid JSON: {e}") from e
        return {name: AuthUser(**data) for name, data in raw.items()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
