"""Startup diagnostics stay off unless explicitly enabled, and never log the key."""

from __future__ import annotations

import hashlib
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.meta_diagnostics import log_meta_runtime_diagnostics

_SECRET = "unit-test-key-not-a-live-credential"


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status = status
        self._body = body

    def read(self, limit: int = -1) -> bytes:
        if limit >= 0:
            return self._body[:limit]
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_diagnostics_are_disabled_by_default(caplog: pytest.LogCaptureFixture) -> None:
    assert load_settings({}).meta_runtime_diagnostics is False
    assert load_settings({"META_RUNTIME_DIAGNOSTICS": "false"}).meta_runtime_diagnostics is False

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        client = TestClient(create_app(load_settings({})))

    assert client.get("/health").status_code == 200
    assert "MODEL_API_KEY" not in caplog.text
    assert "sha256" not in caplog.text
    assert "available_model_ids" not in caplog.text


def test_disabled_startup_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    monkeypatch.setattr("app.meta_diagnostics.request.urlopen", blocked)

    client = TestClient(create_app(load_settings({})))

    assert client.get("/health").json()["status"] == "ok"


def test_fingerprint_is_safe_and_secret_is_absent_from_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[tuple[str, str]] = []

    def fetch(url: str, api_key: str) -> tuple[int, list[str]]:
        seen.append((url, api_key))
        return 200, ["muse-spark-1.3"]

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key=_SECRET,
            meta_base_url="https://api.meta.ai/v1",
            meta_model_id="muse-spark-1.3",
            fetch_models=fetch,
        )

    text = caplog.text
    assert seen == [("https://api.meta.ai/v1/models", _SECRET)]
    assert f"MODEL_API_KEY present: true" in text
    assert f"MODEL_API_KEY length: {len(_SECRET)}" in text
    assert f"MODEL_API_KEY sha256 first 10: {_fingerprint(_SECRET)}" in text
    assert _SECRET not in text
    assert "unit-test" not in text
    assert "credential" not in text
    assert "Authorization" not in text
    assert "Bearer" not in text
    assert "models_http_status: 200" in text
    assert "available_model_ids: ['muse-spark-1.3']" in text
    assert "computed chat completions URL: https://api.meta.ai/v1/chat/completions" in text


def test_repr_exposes_accidental_whitespace(caplog: pytest.LogCaptureFixture) -> None:
    def fetch(url: str, api_key: str) -> tuple[int, list[str]]:
        assert url == "https://api.meta.ai/v1/models"
        assert api_key == ""
        return 200, []

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        log_meta_runtime_diagnostics(
            api_key="",
            meta_base_url="https://api.meta.ai/v1 ",
            meta_model_id=" muse-spark-1.3",
            fetch_models=fetch,
        )

    assert "META_MODEL_ID: ' muse-spark-1.3'" in caplog.text
    assert "META_BASE_URL: 'https://api.meta.ai/v1 '" in caplog.text
    assert "MODEL_API_KEY present: false" in caplog.text


def test_process_environment_keeps_raw_whitespace(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[object] = []

    def fake_urlopen(outgoing: object, timeout: int = 0) -> _Response:
        calls.append(outgoing)
        body = b'{"data":[{"id":"muse-spark-1.3"},{"id":"muse-spark-1.2"}]}'
        return _Response(body)

    monkeypatch.setenv("META_RUNTIME_DIAGNOSTICS", "true")
    monkeypatch.setenv("MODEL_API_KEY", _SECRET)
    monkeypatch.setenv("META_BASE_URL", "https://api.meta.ai/v1 ")
    monkeypatch.setenv("META_MODEL_ID", " muse-spark-1.3")
    monkeypatch.setattr("app.meta_diagnostics.request.urlopen", fake_urlopen)

    with caplog.at_level(logging.WARNING, logger="falsifyai.meta_diagnostics"):
        client = TestClient(create_app())

    assert client.get("/health").status_code == 200
    assert len(calls) == 1
    request = calls[0]
    assert request.get_method() == "GET"  # type: ignore[attr-defined]
    assert request.full_url == "https://api.meta.ai/v1/models"  # type: ignore[attr-defined]
    assert "chat/completions" not in request.full_url  # type: ignore[attr-defined]
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

    monkeypatch.setattr("app.meta_diagnostics.request.urlopen", boom)
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
    assert "models_http_status: unreachable" in caplog.text
