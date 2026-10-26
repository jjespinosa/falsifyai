"""Meta Model API provider.

Live mode checks configuration and still performs no HTTP in this milestone.
"""

from urllib.parse import urlparse

from app.config import Settings
from app.providers.base import ModelCompletion


class ConfigurationError(RuntimeError):
    """Live mode is missing a key, a model id, or a usable base URL."""


class LiveModelCallsDisabled(RuntimeError):
    """Raised when code attempts a live model call before that client exists."""


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

    Construction is the live-mode gate. ``complete`` does not open a socket.
    Tests should use ``StubModelProvider``.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.model_api_key.get_secret_value().strip() == "":
            raise ConfigurationError("MODEL_API_KEY is required for live Meta Model API calls.")
        if settings.meta_model_id.strip() == "":
            raise ConfigurationError("META_MODEL_ID is required for live Meta Model API calls.")
        if not _is_absolute_https_url(settings.meta_base_url):
            raise ConfigurationError(
                "META_BASE_URL must be an absolute https URL for live Meta Model API calls."
            )
        self._settings = settings
        self.model_id = settings.meta_model_id

    @property
    def base_url(self) -> str:
        return self._settings.meta_base_url

    @property
    def api_key_configured(self) -> bool:
        return self._settings.model_api_key.get_secret_value() != ""

    def complete(self, *, system: str, user: str) -> ModelCompletion:
        del system, user
        raise LiveModelCallsDisabled(
            "Live Meta Model API calls are disabled in milestone M0. Use StubModelProvider."
        )

    def __repr__(self) -> str:
        return (
            "MetaModelProvider("
            f"base_url={self.base_url!r}, "
            f"model_id={self.model_id!r}, "
            f"api_key_configured={self.api_key_configured})"
        )
