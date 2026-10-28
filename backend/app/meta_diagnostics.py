"""Temporary startup check for the Meta runtime configuration.

Logs a key fingerprint and the raw model-catalog document.
The API key, request headers, and response headers other than Content-Type
are not logged. This module does not call chat completions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any

import requests

logger = logging.getLogger("falsifyai.meta_diagnostics")

_SENSITIVE_NAME = ("key", "token", "authorization", "secret")
CatalogGet = Callable[..., requests.Response]


def log_meta_runtime_diagnostics(
    *,
    api_key: str,
    meta_base_url: str,
    meta_model_id: str,
    get: CatalogGet | None = None,
) -> None:
    """Log the runtime Meta configuration and one GET /models response.

    A catalog or transport failure is logged and does not propagate.
    """

    try:
        _log(
            api_key=api_key,
            meta_base_url=meta_base_url,
            meta_model_id=meta_model_id,
            get=get or requests.get,
        )
    except Exception:
        logger.warning("meta runtime diagnostics failed")


def _log(
    *,
    api_key: str,
    meta_base_url: str,
    meta_model_id: str,
    get: CatalogGet,
) -> None:
    fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:10]
    normalized = meta_base_url.strip().rstrip("/")
    completions = f"{normalized}/chat/completions" if normalized else ""
    models_url = f"{normalized}/models" if normalized else ""
    logger.warning("MODEL_API_KEY present: %s", "true" if api_key else "false")
    logger.warning("MODEL_API_KEY length: %d", len(api_key))
    logger.warning("MODEL_API_KEY sha256 first 10: %s", fingerprint)
    logger.warning("META_MODEL_ID: %r", meta_model_id)
    logger.warning("META_BASE_URL: %r", meta_base_url)
    logger.warning("computed chat completions URL: %s", completions)
    if models_url == "":
        logger.warning("models_request_error: missing base URL")
        return
    try:
        response = get(
            models_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("models_request_error: %s: %s", type(exc).__name__, _redact_text(str(exc), api_key))
        return
    _describe_catalog(response, api_key=api_key)


def _describe_catalog(response: Any, *, api_key: str) -> None:
    content_type = response.headers.get("Content-Type", "")
    body = response.text if isinstance(response.text, str) else ""
    logger.warning("models_http_status: %s", response.status_code)
    logger.warning("models_content_type: %s", content_type)
    logger.warning("models_body_characters: %d", len(body))
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("models_json_parse_error: %s: %s", type(exc).__name__, exc)
        logger.warning("models_raw_body_prefix: %s", _redact_text(body, api_key)[:2000])
        return
    sanitized = _redact_value(payload)
    rendered = json.dumps(sanitized, ensure_ascii=False)
    logger.warning("models_sanitized_body: %s", _redact_text(rendered, api_key)[:10000])
    if not isinstance(payload, dict):
        logger.warning("models_top_level_type: %s", type(payload).__name__)
        logger.warning("models_data_field: absent")
        return
    logger.warning("models_top_level_keys: %s", sorted(str(name) for name in payload))
    if "data" not in payload:
        logger.warning("models_data_field: absent")
        return
    data = payload["data"]
    logger.warning("models_data_field: present")
    logger.warning("models_data_type: %s", type(data).__name__)
    if not isinstance(data, list):
        logger.warning("models_data_length: not-a-list")
        return
    logger.warning("models_data_length: %d", len(data))
    identifiers = [
        item["id"]
        for item in data
        if isinstance(item, dict) and "id" in item
    ]
    logger.warning("available_model_ids: %s", identifiers)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for name, item in value.items():
            label = str(name)
            if any(part in label.lower() for part in _SENSITIVE_NAME):
                cleaned[label] = "[redacted]"
            else:
                cleaned[label] = _redact_value(item)
        return cleaned
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _redact_text(value: str, api_key: str) -> str:
    if api_key:
        value = value.replace(api_key, "[redacted]")
    return value.replace("Bearer [redacted]", "[redacted]")
