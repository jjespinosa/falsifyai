"""Startup diagnostics stay off unless explicitly enabled, and never log the key."""

from __future__ import annotations

import hashlib
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.meta_diagnostics import log_meta_runtime_diagnostics

_SECRET = "unit-test-key-not-a-live-credential"


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


class _CatalogResponse:
    def __init__(self, body: str, status_code: int = 200, content_type: str = "application/json") -> None:
        self.status_code = status_code
        self.text = body
        self.headers = {"Content-Type": content_type}


def _catalog(body: dict[str, object] | str, status_code: int = 200) -> _CatalogResponse:
    text = body if isinstance(body, str) else json.dumps(body)
    return _CatalogResponse(text, status_code=status_code)


def test_diagnostics_are_disabled_by_default(caplog: pytest.LogCaptureFixture) -> None:
    assert load_settings({}).meta_runtime_diagnostics is False
    assert load_settings({"META_RUNTIME_DIAGNOSTICS": "false"}).meta_runtime_diagnostics is False

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        client = TestClient(create_app(load_settings({})))

    assert client.get("/health").status_code == 200
    assert "sha256" not in caplog.text
    assert "available_model_ids" not in caplog.text
    assert "models_sanitized_body" not in caplog.text


def test_disabled_startup_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    monkeypatch.setattr("app.meta_diagnostics.requests.get", blocked)

    client = TestClient(create_app(load_settings({})))

    assert client.get("/health").json()["status"] == "ok"


def test_fingerprint_is_safe_and_models_are_parsed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[tuple[object, ...]] = []

    def get(url: str, headers: dict[str, str], timeout: int) -> _CatalogResponse:
        seen.append((url, headers, timeout))
        return _catalog({"object": "list", "data": [{"id": "muse-spark-1.3"}, {"name": "unnamed"}]})

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key=_SECRET,
            meta_base_url="https://api.meta.ai/v1",
            meta_model_id="muse-spark-1.3",
            get=get,
        )

    text = caplog.text
    assert seen == [(
        "https://api.meta.ai/v1/models",
        {"Authorization": f"Bearer {_SECRET}"},
        10,
    )]
    assert "MODEL_API_KEY present: true" in text
    assert f"MODEL_API_KEY length: {len(_SECRET)}" in text
    assert f"MODEL_API_KEY sha256 first 10: {_fingerprint(_SECRET)}" in text
    assert _SECRET not in text
    assert "unit-test" not in text
    assert "credential" not in text
    assert "Authorization" not in text
    assert "Bearer" not in text
    assert "models_http_status: 200" in text
    assert "models_content_type: application/json" in text
    assert "models_data_field: present" in text
    assert "models_data_type: list" in text
    assert "models_data_length: 2" in text
    assert "available_model_ids: ['muse-spark-1.3']" in text
    assert "computed chat completions URL: https://api.meta.ai/v1/chat/completions" in text


def test_empty_data_is_reported_as_empty(caplog: pytest.LogCaptureFixture) -> None:
    def get(url: str, headers: dict[str, str], timeout: int) -> _CatalogResponse:
        return _catalog({"data": []})

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key="",
            meta_base_url="https://api.meta.ai/v1",
            meta_model_id="muse-spark-1.3",
            get=get,
        )

    assert "models_data_field: present" in caplog.text
    assert "models_data_length: 0" in caplog.text
    assert "available_model_ids: []" in caplog.text
    assert "models_data_field: absent" not in caplog.text


def test_missing_data_field_is_distinct_from_empty_data(caplog: pytest.LogCaptureFixture) -> None:
    def get(url: str, headers: dict[str, str], timeout: int) -> _CatalogResponse:
        return _catalog({"object": "list", "models": [{"id": "muse-spark-1.3"}]})

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key="",
            meta_base_url="https://api.meta.ai/v1",
            meta_model_id="muse-spark-1.3",
            get=get,
        )

    assert "models_top_level_keys: ['models', 'object']" in caplog.text
    assert "models_data_field: absent" in caplog.text
    assert "models_data_length" not in caplog.text
    assert "available_model_ids" not in caplog.text


def test_malformed_json_is_not_converted_to_an_empty_list(caplog: pytest.LogCaptureFixture) -> None:
    def get(url: str, headers: dict[str, str], timeout: int) -> _CatalogResponse:
        return _CatalogResponse("not-json {", content_type="text/plain")

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key=_SECRET,
            meta_base_url="https://api.meta.ai/v1",
            meta_model_id="muse-spark-1.3",
            get=get,
        )

    assert "models_json_parse_error: JSONDecodeError:" in caplog.text
    assert "models_raw_body_prefix: not-json {" in caplog.text
    assert "available_model_ids: []" not in caplog.text
    assert _SECRET not in caplog.text


def test_secret_like_fields_are_redacted(caplog: pytest.LogCaptureFixture) -> None:
    def get(url: str, headers: dict[str, str], timeout: int) -> _CatalogResponse:
        return _catalog(
            {
                "data": [{"id": "muse-spark-1.3", "api_key": _SECRET}],
                "access_token": "tok-value",
                "authorization": "Bearer hidden",
                "client_secret": "hidden-secret",
            }
        )

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key=_SECRET,
            meta_base_url="https://api.meta.ai/v1",
            meta_model_id="muse-spark-1.3",
            get=get,
        )

    assert _SECRET not in caplog.text
    assert "tok-value" not in caplog.text
    assert "hidden-secret" not in caplog.text
    assert "Bearer hidden" not in caplog.text
    assert "[redacted]" in caplog.text
    assert "available_model_ids: ['muse-spark-1.3']" in caplog.text


def test_repr_exposes_accidental_whitespace(caplog: pytest.LogCaptureFixture) -> None:
    def get(url: str, headers: dict[str, str], timeout: int) -> _CatalogResponse:
        assert url == "https://api.meta.ai/v1/models"
        assert timeout == 10
        return _catalog({"data": []})

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key="",
            meta_base_url="https://api.meta.ai/v1 ",
            meta_model_id=" muse-spark-1.3",
            get=get,
        )

    assert "META_MODEL_ID: ' muse-spark-1.3'" in caplog.text
    assert "META_BASE_URL: 'https://api.meta.ai/v1 '" in caplog.text
    assert "MODEL_API_KEY present: false" in caplog.text


def test_process_environment_keeps_raw_whitespace(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict[str, str], timeout: int) -> _CatalogResponse:
        calls.append(url)
        assert timeout == 10
        assert set(headers) == {"Authorization"}
        return _catalog({"data": [{"id": "muse-spark-1.3"}, {"id": "muse-spark-1.2"}]})

    monkeypatch.setenv("META_RUNTIME_DIAGNOSTICS", "true")
    monkeypatch.setenv("MODEL_API_KEY", _SECRET)
    monkeypatch.setenv("META_BASE_URL", "https://api.meta.ai/v1 ")
    monkeypatch.setenv("META_MODEL_ID", " muse-spark-1.3")
    monkeypatch.setattr("app.meta_diagnostics.requests.get", fake_get)

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        client = TestClient(create_app())

    assert client.get("/health").status_code == 200
    assert calls == ["https://api.meta.ai/v1/models"]
    assert _SECRET not in caplog.text
    assert "META_MODEL_ID: ' muse-spark-1.3'" in caplog.text
    assert "META_BASE_URL: 'https://api.meta.ai/v1 '" in caplog.text
    assert "available_model_ids: ['muse-spark-1.3', 'muse-spark-1.2']" in caplog.text


def test_catalog_failure_does_not_stop_startup(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"Bearer {_SECRET}")

    monkeypatch.setattr("app.meta_diagnostics.requests.get", boom)
    settings = load_settings(
        {
            "META_RUNTIME_DIAGNOSTICS": "true",
            "MODEL_API_KEY": _SECRET,
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "muse-spark-1.3",
        }
    )

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        client = TestClient(create_app(settings))

    assert client.get("/health").json()["milestone"] == "M7"
    assert _SECRET not in caplog.text
    assert "Bearer" not in caplog.text
    assert "models_request_error: RuntimeError:" in caplog.text
