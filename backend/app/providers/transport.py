"""HTTP transport for the Meta chat-completions endpoint.

Tests inject their own transport. The default suite does not construct this one.
"""

from __future__ import annotations

import json
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
    """Stdlib client for an explicitly enabled live call."""

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> dict[str, object]:
        payload = json.dumps(body).encode("utf-8")
        outgoing = request.Request(url, data=payload, headers=dict(headers), method="POST")
        try:
            with request.urlopen(outgoing, timeout=60) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ProviderResponseError(f"The Meta Model API returned HTTP {code}.") from None
        except error.URLError:
            raise ProviderResponseError("The Meta Model API could not be reached.") from None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise ProviderResponseError("The Meta Model API returned a non-JSON payload.") from None
        if not isinstance(parsed, dict):
            raise ProviderResponseError("The Meta Model API returned an unexpected payload.")
        return parsed
