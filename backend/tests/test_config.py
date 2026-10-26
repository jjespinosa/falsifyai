"""Tests for environment configuration."""

import hashlib

import pytest
from pydantic import ValidationError

from app.config import DEFAULT_META_BASE_URL, load_settings

_FAKE_KEY = "unit-test-not-a-secret"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_defaults_when_variables_are_absent() -> None:
    settings = load_settings({})

    assert settings.meta_base_url == DEFAULT_META_BASE_URL
    assert settings.meta_model_id == ""
    assert settings.model_api_key.get_secret_value() == ""
    assert settings.model_dump()["model_api_key"] == ""


def test_empty_model_id_does_not_select_a_model() -> None:
    absent = load_settings({"META_BASE_URL": "https://api.meta.ai/v1"})
    blank = load_settings(
        {
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "   ",
        }
    )

    assert absent.meta_model_id == ""
    assert blank.meta_model_id == ""


def test_verified_primary_configuration_is_accepted() -> None:
    settings = load_settings(
        {
            "MODEL_API_KEY": _FAKE_KEY,
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "muse-spark-1.3",
        }
    )

    assert settings.meta_base_url == "https://api.meta.ai/v1"
    assert settings.meta_model_id == "muse-spark-1.3"


def test_explicit_mapping_overrides_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", _FAKE_KEY)
    monkeypatch.setenv("META_BASE_URL", "https://from-process.example/v1")
    monkeypatch.setenv("META_MODEL_ID", "other-model")

    settings = load_settings({})

    assert settings.model_api_key.get_secret_value() == ""
    assert settings.meta_base_url == DEFAULT_META_BASE_URL
    assert settings.meta_model_id == ""


def test_reads_values_from_the_supplied_environment() -> None:
    settings = load_settings(
        {
            "MODEL_API_KEY": _FAKE_KEY,
            "META_BASE_URL": "https://example.test/v1/",
            "META_MODEL_ID": "muse-spark-1.3",
        }
    )

    assert _digest(settings.model_api_key.get_secret_value()) == _digest(_FAKE_KEY)
    assert settings.meta_base_url == "https://example.test/v1"
    assert settings.meta_model_id == "muse-spark-1.3"
    assert _FAKE_KEY not in repr(settings)
    assert _FAKE_KEY not in str(settings)
    assert settings.model_dump()["model_api_key"] == "***"
    assert _FAKE_KEY not in settings.model_dump_json()


def test_process_environment_is_used_when_no_mapping_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_API_KEY", _FAKE_KEY)
    monkeypatch.setenv("META_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("META_MODEL_ID", "muse-spark-1.3")

    settings = load_settings()

    assert _digest(settings.model_api_key.get_secret_value()) == _digest(_FAKE_KEY)
    assert _FAKE_KEY not in repr(settings)


def test_rejects_non_https_base_url() -> None:
    with pytest.raises(ValidationError):
        load_settings({"META_BASE_URL": "http://api.meta.ai/v1"})


def test_rejects_malformed_model_id() -> None:
    with pytest.raises(ValidationError):
        load_settings({"META_MODEL_ID": "../secret"})
