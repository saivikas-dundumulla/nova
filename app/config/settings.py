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

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-06-01"
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_temperature: float = 0.1

    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "ombuds-knowledge"
    azure_search_field_source_type: str = "source_type"
    azure_search_field_incident_number: str = "incident_number"
    azure_search_field_title: str = "title"
    azure_search_field_content: str = "content"
    azure_search_field_url: str = "url"
    azure_search_semantic_config: str = "default"
    azure_search_top_k: int = 8

    # Kibana
    kibana_url: str = ""
    kibana_api_key: str = ""
    kibana_index_pattern: str = "logs-*"
    kibana_default_time_range: str = "24h"
    kibana_timeout_seconds: float = 10.0
    kibana_max_hits: int = 25

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
