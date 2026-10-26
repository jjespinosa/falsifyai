"""Tests for the M0 model-provider seam."""

import pytest
from pydantic import SecretStr

from app.config import Settings, load_settings
from app.main import create_app
from app.providers.meta import ConfigurationError, LiveModelCallsDisabled, MetaModelProvider
from app.providers.stub import StubModelProvider

_FAKE_KEY = "unit-test-not-a-secret"


def test_stub_returns_scripted_text_without_calling_out() -> None:
    provider = StubModelProvider(model_id="muse-spark-1.3", content="scripted-observation")

    completion = provider.complete(system="Criticize.", user="Salinity lowers germination.")

    assert completion.stub is True
    assert completion.model_id == "muse-spark-1.3"
    assert completion.content == "scripted-observation"
    assert provider.prompts == [("Criticize.", "Salinity lowers germination.")]


def test_stub_rejects_an_empty_user_prompt() -> None:
    provider = StubModelProvider(model_id="muse-spark-1.3")

    with pytest.raises(ValueError):
        provider.complete(system="", user="  ")


def test_meta_provider_refuses_live_calls_and_hides_the_key() -> None:
    settings = load_settings(
        {
            "MODEL_API_KEY": _FAKE_KEY,
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "muse-spark-1.3",
        }
    )
    provider = MetaModelProvider(settings)

    assert provider.base_url == "https://api.meta.ai/v1"
    assert provider.model_id == "muse-spark-1.3"
    assert provider.api_key_configured is True
    assert _FAKE_KEY not in repr(provider)
    with pytest.raises(LiveModelCallsDisabled):
        provider.complete(system="Criticize.", user="State the observable.")


def test_missing_api_key_prevents_live_provider_use() -> None:
    settings = load_settings(
        {
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "muse-spark-1.3",
        }
    )

    with pytest.raises(ConfigurationError, match="MODEL_API_KEY"):
        MetaModelProvider(settings)


def test_missing_model_id_prevents_live_provider_use() -> None:
    settings = load_settings(
        {
            "MODEL_API_KEY": _FAKE_KEY,
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "",
        }
    )

    with pytest.raises(ConfigurationError, match="META_MODEL_ID"):
        MetaModelProvider(settings)


def test_invalid_base_url_prevents_live_provider_use() -> None:
    settings = Settings.model_construct(
        model_api_key=SecretStr(_FAKE_KEY),
        meta_base_url="http://api.meta.ai/v1",
        meta_model_id="muse-spark-1.3",
    )

    with pytest.raises(ConfigurationError, match="META_BASE_URL"):
        MetaModelProvider(settings)


def test_valid_live_configuration_initializes_without_a_request() -> None:
    settings = load_settings(
        {
            "MODEL_API_KEY": _FAKE_KEY,
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "muse-spark-1.3",
        }
    )

    provider = MetaModelProvider(settings)

    assert provider.base_url == "https://api.meta.ai/v1"
    assert provider.model_id == "muse-spark-1.3"
    with pytest.raises(LiveModelCallsDisabled):
        provider.complete(system="Criticize.", user="State the observable.")


def test_application_shell_uses_the_stub() -> None:
    app = create_app(
        load_settings(
            {
                "META_BASE_URL": "https://api.meta.ai/v1",
                "META_MODEL_ID": "muse-spark-1.3",
            }
        )
    )

    completion = app.state.provider.complete(system="Stand by.", user="A hypothesis.")

    assert isinstance(app.state.provider, StubModelProvider)
    assert completion.stub is True
    assert completion.model_id == "muse-spark-1.3"


def test_http_error_keeps_a_schema_message_and_drops_bearer_tokens() -> None:
    from io import BytesIO
    from urllib.error import HTTPError

    from app.providers.transport import _read_error_body, _usage

    body = b'{"error":{"message":"schema rejected Bearer super-secret-token"}}'
    exc = HTTPError(
        "https://api.meta.ai/v1/chat/completions",
        400,
        "Bad Request",
        hdrs={},
        fp=BytesIO(body),
    )

    detail = _read_error_body(exc)

    assert detail == "schema rejected Bearer [redacted]"
    assert "super-secret-token" not in detail
    assert _usage(
        {
            "prompt_tokens": 3,
            "completion_tokens": 4,
            "total_tokens": 7,
            "completion_tokens_details": {"reasoning_tokens": 2, "reasoning": "hidden"},
        }
    ) == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
        "reasoning_tokens": 2,
    }
    assert "hidden" not in str(
        _usage({"completion_tokens_details": {"reasoning_tokens": 2, "reasoning": "hidden"}})
    )
    assert _usage({"prompt_tokens": "3"}) is None
