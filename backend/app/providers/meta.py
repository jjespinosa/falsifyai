"""Meta Model API provider.

A live call happens only when a transport is attached. The object still
refuses to open a socket by itself.
"""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from app.config import Settings
from app.providers.base import ModelCompletion


class ConfigurationError(RuntimeError):
    """Live mode is missing a key, a model id, or a usable base URL."""


class LiveModelCallsDisabled(RuntimeError):
    """Raised when a live call is attempted without an attached transport."""


REASONING_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh", "max"})


class ProviderResponseError(RuntimeError):
    """The live call failed, or the payload did not match the schema."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        stage: str = "validation",
        diagnostic: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.stage = stage
        self.diagnostic = diagnostic


def _is_absolute_https_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and not parsed.username
        and not parsed.password
    )


class MetaModelProvider:
    """Configured handle for the Meta Model API.

    Construction checks configuration. ``complete`` sends HTTP only when
    ``transport`` is attached. Tests keep the transport unset or fake.
    """

    def __init__(self, settings: Settings, *, transport: Any | None = None) -> None:
        if settings.model_api_key.get_secret_value().strip() == "":
            raise ConfigurationError("MODEL_API_KEY is required for live Meta Model API calls.")
        if settings.meta_model_id.strip() == "":
            raise ConfigurationError("META_MODEL_ID is required for live Meta Model API calls.")
        if not _is_absolute_https_url(settings.meta_base_url):
            raise ConfigurationError(
                "META_BASE_URL must be an absolute https URL for live Meta Model API calls."
            )
        self._settings = settings
        self._transport = transport
        self.model_id = settings.meta_model_id

    @property
    def base_url(self) -> str:
        return self._settings.meta_base_url

    @property
    def api_key_configured(self) -> bool:
        return self._settings.model_api_key.get_secret_value() != ""

    def complete(
        self,
        *,
        system: str,
        user: str,
        response_schema: Mapping[str, Any] | None = None,
        schema_name: str | None = None,
        reasoning_effort: str | None = None,
    ) -> ModelCompletion:
        """Call chat completions when a transport is attached.

        The API key is sent only in the Authorization header. It is not placed
        in the JSON body and it is not included in error text.
        """

        if user.strip() == "":
            raise ValueError("user prompt must not be empty")
        if self._transport is None:
            raise LiveModelCallsDisabled(
                "No live transport is attached. Refusing to call the Meta Model API."
            )
        body: dict[str, object] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if response_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name or "StructuredResult",
                    "strict": True,
                    "schema": dict(response_schema),
                },
            }
        if reasoning_effort is not None:
            if reasoning_effort not in REASONING_EFFORTS:
                raise ValueError(
                    "reasoning_effort must be minimal, low, medium, high, xhigh, or max."
                )
            body["reasoning_effort"] = reasoning_effort
        key = self._settings.model_api_key.get_secret_value()
        payload = self._transport.post_json(
            url=f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            body=body,
        )
        return ModelCompletion(
            model_id=self.model_id,
            content=_message_content(payload),
            stub=False,
        )

    def __repr__(self) -> str:
        return (
            "MetaModelProvider("
            f"base_url={self.base_url!r}, "
            f"model_id={self.model_id!r}, "
            f"api_key_configured={self.api_key_configured})"
        )


def _message_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ProviderResponseError("The live model response did not include a message.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderResponseError("The live model response did not include a message.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("The live model response did not include a message.")
    content = message.get("content")
    if not isinstance(content, str) or content.strip() == "":
        raise ProviderResponseError("The live model response did not include a message.")
    return content
