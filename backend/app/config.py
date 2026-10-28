"""Runtime settings read from the process environment.

This module does not open a dotenv file and does not log secrets.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, SecretStr, field_serializer, field_validator

DEFAULT_META_BASE_URL = "https://api.meta.ai/v1"
REDACTED_SECRET = "***"

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class Settings(BaseModel):
    """Configuration for the Meta Model API client and the public demo limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_api_key: SecretStr = SecretStr("")
    meta_base_url: str = DEFAULT_META_BASE_URL
    meta_model_id: str = ""
    live_runs_enabled: bool = True
    max_hypothesis_length: int = 4_000
    max_request_bytes: int = 65_536
    live_run_limit: int = 4
    live_run_window_seconds: int = 3_600

    @field_validator("meta_base_url", mode="before")
    @classmethod
    def _https_base_url(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("META_BASE_URL must be an absolute https URL")
        candidate = value.strip().rstrip("/")
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("META_BASE_URL must be an absolute https URL")
        return candidate

    @field_validator("meta_model_id", mode="before")
    @classmethod
    def _model_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("META_MODEL_ID must be a model identifier")
        candidate = value.strip()
        if candidate == "":
            return ""
        if _MODEL_ID.fullmatch(candidate) is None:
            raise ValueError("META_MODEL_ID must be a model identifier")
        return candidate

    @field_validator("live_runs_enabled", mode="before")
    @classmethod
    def _live_flag(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if not isinstance(value, str):
            raise ValueError("LIVE_RUNS_ENABLED must be true or false")
        token = value.strip().lower()
        if token in {"1", "true", "yes", "on"}:
            return True
        if token in {"0", "false", "no", "off"}:
            return False
        raise ValueError("LIVE_RUNS_ENABLED must be true or false")

    @field_validator("max_hypothesis_length")
    @classmethod
    def _hypothesis_bound(cls, value: int) -> int:
        if value < 1 or value > 4_000:
            raise ValueError("MAX_HYPOTHESIS_LENGTH must be from 1 to 4000")
        return value

    @field_validator("max_request_bytes")
    @classmethod
    def _body_bound(cls, value: int) -> int:
        if value < 1_024 or value > 1_048_576:
            raise ValueError("MAX_REQUEST_BYTES must be from 1024 to 1048576")
        return value

    @field_validator("live_run_limit")
    @classmethod
    def _run_limit(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("LIVE_RUN_LIMIT must be from 1 to 100")
        return value

    @field_validator("live_run_window_seconds")
    @classmethod
    def _run_window(cls, value: int) -> int:
        if value < 60 or value > 86_400:
            raise ValueError("LIVE_RUN_WINDOW_SECONDS must be from 60 to 86400")
        return value

    @field_serializer("model_api_key")
    def _redact_api_key(self, value: SecretStr) -> str:
        if value.get_secret_value() == "":
            return ""
        return REDACTED_SECRET

    def __repr__(self) -> str:
        key = self.model_api_key.get_secret_value()
        shown = REDACTED_SECRET if key else ""
        return (
            "Settings("
            f"model_api_key={shown!r}, "
            f"meta_base_url={self.meta_base_url!r}, "
            f"meta_model_id={self.meta_model_id!r}, "
            f"live_runs_enabled={self.live_runs_enabled!r})"
        )

    def __str__(self) -> str:
        return repr(self)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load settings from environment variables.

    An explicit mapping is used by tests so they never read a developer machine.
    When the mapping is omitted, only ``os.environ`` is consulted.
    """

    source = os.environ if environ is None else environ
    payload: dict[str, object] = {
        "model_api_key": SecretStr(source.get("MODEL_API_KEY", "")),
        "meta_base_url": source.get("META_BASE_URL", DEFAULT_META_BASE_URL),
        "meta_model_id": source.get("META_MODEL_ID", ""),
    }
    if "LIVE_RUNS_ENABLED" in source:
        payload["live_runs_enabled"] = source["LIVE_RUNS_ENABLED"]
    for name, field in (
        ("MAX_HYPOTHESIS_LENGTH", "max_hypothesis_length"),
        ("MAX_REQUEST_BYTES", "max_request_bytes"),
        ("LIVE_RUN_LIMIT", "live_run_limit"),
        ("LIVE_RUN_WINDOW_SECONDS", "live_run_window_seconds"),
    ):
        if name in source and source[name].strip() != "":
            payload[field] = int(source[name])
    return Settings.model_validate(payload)
