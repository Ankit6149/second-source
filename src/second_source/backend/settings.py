"""Explicit server configuration; importing this module reads no environment."""
from __future__ import annotations

import json
from typing import Literal, Mapping
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, SecretStr, field_validator
from second_source.contracts import StrictModel


class CloudSettings(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_ref: Literal["jpqcqqbzriizxhigvjki"] = "jpqcqqbzriizxhigvjki"
    database_url: SecretStr = Field(repr=False)
    publishable_key: SecretStr = Field(repr=False)
    storage_key: SecretStr = Field(repr=False)
    cors_origins: tuple[str, ...] = ()
    enable_mock_execution: bool = False
    max_concurrent_requests: int = Field(default=8, ge=1, le=16)
    requests_per_minute: int = Field(default=60, ge=1, le=120)

    @field_validator("database_url", "publishable_key", "storage_key")
    @classmethod
    def bounded_secret(cls, value):
        raw = value.get_secret_value()
        if not 20 <= len(raw) <= 4096 or any(c in raw for c in "\r\n\x00"):
            raise ValueError("Invalid server configuration")
        return value

    @field_validator("cors_origins")
    @classmethod
    def exact_origins(cls, values):
        if len(values) > 8 or len(set(values)) != len(values):
            raise ValueError("Invalid CORS origins")
        for value in values:
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or not parsed.hostname or "*" in value
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path or parsed.port not in (None, 443)):
                raise ValueError("CORS origins must be exact HTTPS origins")
        return values

    @classmethod
    def from_environment(cls, values: Mapping[str, str]):
        """Use only caller-supplied server values, never load .env or log inputs."""
        try:
            enabled = values.get("SECOND_SOURCE_ENABLE_MOCK_EXECUTION", "false")
            if enabled not in ("true", "false"):
                raise ValueError
            origins = json.loads(values.get("SECOND_SOURCE_CORS_ORIGINS", "[]"))
            if not isinstance(origins, list) or not all(isinstance(v, str) for v in origins):
                raise ValueError
            return cls(database_url=values["SECOND_SOURCE_DATABASE_URL"],
                       publishable_key=values["SECOND_SOURCE_SUPABASE_PUBLISHABLE_KEY"],
                       storage_key=values["SECOND_SOURCE_STORAGE_SERVER_KEY"],
                       project_ref=values.get("SECOND_SOURCE_SUPABASE_PROJECT_REF", "jpqcqqbzriizxhigvjki"),
                       cors_origins=tuple(origins), enable_mock_execution=enabled == "true")
        except Exception:
            raise ValueError("Required cloud server configuration is unavailable or invalid") from None
