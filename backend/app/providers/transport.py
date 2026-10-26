"""HTTP transport for the Meta chat-completions endpoint.

Tests inject their own transport. The default suite does not construct this one.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Protocol
from urllib import error, request

from app.providers.meta import ProviderResponseError


class ModelTransport(Protocol):
    """One JSON POST. Implementations must not log headers."""

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> dict[str, object]:
        """Send ``body`` and return the decoded JSON object."""


class UrllibTransport:
    """Stdlib client for an explicitly enabled live call.

    ``last_usage`` keeps token counts from the latest response. It never stores
    request headers.
    """

    def __init__(self) -> None:
        self.last_usage: dict[str, int] | None = None
        self.last_http_status: int | None = None
        self.last_finish_reason: str | None = None
        self.last_response_model: str | None = None
        self.last_body: dict[str, object] | None = None
        self.last_visible_characters: int | None = None

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> dict[str, object]:
        self.last_usage = None
        self.last_http_status = None
        self.last_finish_reason = None
        self.last_response_model = None
        self.last_body = None
        self.last_visible_characters = None
        payload = json.dumps(body).encode("utf-8")
        outgoing = request.Request(url, data=payload, headers=dict(headers), method="POST")
        try:
            with request.urlopen(outgoing, timeout=60) as response:  # noqa: S310
                self.last_http_status = getattr(response, "status", None)
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            code = exc.code
            self.last_http_status = code
            detail = _read_error_body(exc)
            exc.close()
            raise ProviderResponseError(
                f"The Meta Model API returned HTTP {code}. {detail}".strip(),
                http_status=code,
                stage="transport",
            ) from None
        except error.URLError:
            raise ProviderResponseError(
                "The Meta Model API could not be reached.",
                stage="transport",
            ) from None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise ProviderResponseError(
                "The Meta Model API returned a non-JSON payload.",
                stage="transport",
            ) from None
        if not isinstance(parsed, dict):
            raise ProviderResponseError(
                "The Meta Model API returned an unexpected payload.",
                stage="transport",
            )
        self.last_usage = _usage(parsed.get("usage"))
        self.last_visible_characters = _visible_characters(parsed)
        self.last_finish_reason = _finish_reason(parsed)
        model = parsed.get("model")
        self.last_response_model = model if isinstance(model, str) else None
        self.last_body = parsed
        return parsed


def _read_error_body(exc: error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    message = ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        error_body = payload.get("error")
        if isinstance(error_body, dict) and isinstance(error_body.get("message"), str):
            message = error_body["message"]
        elif isinstance(payload.get("message"), str):
            message = payload["message"]
    if not message:
        message = " ".join(raw.split())
    message = message.replace("\n", " ")[:800]
    return re.sub(r"Bearer\s+\S+", "Bearer [redacted]", message)


def _finish_reason(payload: dict[str, object]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    reason = choices[0].get("finish_reason")
    if isinstance(reason, str):
        return reason
    return None


def _visible_characters(payload: dict[str, object]) -> int | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return len(content)
    return None


def _usage(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    allowed = ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens")
    usage = {key: value[key] for key in allowed if isinstance(value.get(key), int)}
    details = value.get("completion_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), int):
        usage["reasoning_tokens"] = details["reasoning_tokens"]
    return usage or None
