"""Temporary startup check for the Meta runtime configuration.

Logs a key fingerprint, the configured endpoint, and the model catalog.
The API key, request headers, and response headers are not logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from urllib import error, request

logger = logging.getLogger("falsifyai.meta_diagnostics")

ModelCatalog = Callable[[str, str], tuple[int | None, list[str]]]


def log_meta_runtime_diagnostics(
    *,
    api_key: str,
    meta_base_url: str,
    meta_model_id: str,
    fetch_models: ModelCatalog | None = None,
) -> None:
    """Log the runtime Meta configuration and one model-catalog response.

    Failures are swallowed. This function does not call chat completions.
    """

    try:
        _log(
            api_key=api_key,
            meta_base_url=meta_base_url,
            meta_model_id=meta_model_id,
            fetch_models=fetch_models or _fetch_model_catalog,
        )
    except Exception:
        logger.warning("meta runtime diagnostics failed")


def _log(
    *,
    api_key: str,
    meta_base_url: str,
    meta_model_id: str,
    fetch_models: ModelCatalog,
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
        logger.warning("models_http_status: unreachable")
        logger.warning("available_model_ids: []")
        return
    status, model_ids = fetch_models(models_url, api_key)
    logger.warning(
        "models_http_status: %s",
        "unreachable" if status is None else status,
    )
    logger.warning("available_model_ids: %s", model_ids)


def _fetch_model_catalog(url: str, api_key: str) -> tuple[int | None, list[str]]:
    """GET the model catalog once. The key is sent and then discarded."""

    outgoing = request.Request(url, method="GET")
    if api_key:
        outgoing.add_header("Authorization", f"Bearer {api_key}")
    try:
        with request.urlopen(outgoing, timeout=20) as response:  # noqa: S310
            status = getattr(response, "status", None)
            raw = response.read(1_000_000)
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        return status, []
    except Exception:
        return None, []
    return status, _model_ids(raw)


def _model_ids(raw: bytes) -> list[str]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        entries = payload.get("data", payload.get("models"))
    elif isinstance(payload, list):
        entries = payload
    else:
        return []
    if not isinstance(entries, list):
        return []
    found: list[str] = []
    for item in entries:
        if isinstance(item, str) and item:
            found.append(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
            found.append(item["id"])
    return found
