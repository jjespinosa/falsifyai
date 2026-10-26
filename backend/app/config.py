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
    """Configuration for the Meta Model API client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_api_key: SecretStr = SecretStr("")
    meta_base_url: str = DEFAULT_META_BASE_URL
    meta_model_id: str = ""

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
            f"meta_model_id={self.meta_model_id!r})"
        )

    def __str__(self) -> str:
        return repr(self)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load settings from environment variables.

    An explicit mapping is used by tests so they never read a developer machine.
    When the mapping is omitted, only ``os.environ`` is consulted.
    """

    source = os.environ if environ is None else environ
    return Settings(
        model_api_key=SecretStr(source.get("MODEL_API_KEY", "")),
        meta_base_url=source.get("META_BASE_URL", DEFAULT_META_BASE_URL),
        meta_model_id=source.get("META_MODEL_ID", ""),
    )
