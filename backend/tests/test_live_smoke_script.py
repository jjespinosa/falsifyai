"""The live canary stays out of the normal suite."""

import importlib.util
import os
from pathlib import Path

import pytest

_FILE_SECRET = "LLM_file_not_a_real_secret"
_PROCESS_SECRET = "LLM_process_not_a_real_secret"
_ENV_NAMES = ("MODEL_API_KEY", "META_BASE_URL", "META_MODEL_ID")


def _load_smoke_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "live_m1_smoke.py"
    spec = importlib.util.spec_from_file_location("live_m1_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during smoke-script import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    module = _load_smoke_module()

    assert module.HYPOTHESIS.startswith("For a simple pendulum")
    assert module.__name__ != "__main__"
    assert module.env_file().is_file()
    assert module.repo_root() == Path(__file__).resolve().parents[2]


def test_repository_root_env_is_loaded_when_process_vars_are_unset(tmp_path: Path) -> None:
    module = _load_smoke_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                f"MODEL_API_KEY={_FILE_SECRET}",
                "META_BASE_URL=https://api.meta.ai/v1",
                "META_MODEL_ID=muse-spark-1.3",
            ]
        ),
        encoding="utf-8",
    )
    previous = {name: os.environ.get(name) for name in _ENV_NAMES}
    for name in _ENV_NAMES:
        os.environ.pop(name, None)
    try:
        detected = module.load_repo_env(tmp_path)
        rendered = "\n".join(
            module.preflight_lines(
                env_detected=detected,
                key=os.environ["MODEL_API_KEY"],
                base_url=os.environ["META_BASE_URL"],
                model_id=os.environ["META_MODEL_ID"],
            )
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    assert detected is True
    assert "MODEL_API_KEY present: true" in rendered
    assert "key prefix valid: true" in rendered
    assert f"key length: {len(_FILE_SECRET)}" in rendered
    assert "META_BASE_URL: https://api.meta.ai/v1" in rendered
    assert "META_MODEL_ID: muse-spark-1.3" in rendered
    assert ".env file detected: true" in rendered
    assert _FILE_SECRET not in rendered


def test_process_environment_overrides_repo_env(tmp_path: Path) -> None:
    module = _load_smoke_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                f"MODEL_API_KEY={_FILE_SECRET}",
                "META_BASE_URL=https://file.example/v1",
                "META_MODEL_ID=from-file",
            ]
        ),
        encoding="utf-8",
    )
    previous = {name: os.environ.get(name) for name in _ENV_NAMES}
    os.environ["MODEL_API_KEY"] = _PROCESS_SECRET
    os.environ["META_BASE_URL"] = "https://process.example/v1"
    os.environ["META_MODEL_ID"] = "from-process"
    try:
        detected = module.load_repo_env(tmp_path)
        key = os.environ["MODEL_API_KEY"]
        base_url = os.environ["META_BASE_URL"]
        model_id = os.environ["META_MODEL_ID"]
        rendered = "\n".join(
            module.preflight_lines(
                env_detected=detected,
                key=key,
                base_url=base_url,
                model_id=model_id,
            )
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    assert detected is True
    assert key == _PROCESS_SECRET
    assert base_url == "https://process.example/v1"
    assert model_id == "from-process"
    assert _FILE_SECRET not in rendered
    assert _PROCESS_SECRET not in rendered


def test_missing_env_file_is_reported_without_a_secret(tmp_path: Path) -> None:
    module = _load_smoke_module()

    detected = module.load_repo_env(tmp_path)
    rendered = "\n".join(
        module.preflight_lines(
            env_detected=detected,
            key="",
            base_url="",
            model_id="",
        )
    )

    assert detected is False
    assert "MODEL_API_KEY present: false" in rendered
    assert "key prefix valid: false" in rendered
    assert "key length: 0" in rendered
    assert ".env file detected: false" in rendered


def test_m2_smoke_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during m2 smoke-script import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    path = Path(__file__).resolve().parents[2] / "scripts" / "live_m2_smoke.py"
    spec = importlib.util.spec_from_file_location("live_m2_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.CASE_MASS.startswith("At fixed pendulum length")
    assert module.__name__ != "__main__"


def test_m3_smoke_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during m3 smoke-script import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    path = Path(__file__).resolve().parents[2] / "scripts" / "live_m3_smoke.py"
    spec = importlib.util.spec_from_file_location("live_m3_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.CASE_MASS.startswith("At fixed pendulum length")
    assert module.__name__ != "__main__"


def test_m4_smoke_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during m4 smoke-script import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    path = Path(__file__).resolve().parents[2] / "scripts" / "live_m4_smoke.py"
    spec = importlib.util.spec_from_file_location("live_m4_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.CASE_MASS.startswith("At fixed pendulum length")
    assert module.__name__ != "__main__"


def test_m5_smoke_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during m5 smoke-script import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    path = Path(__file__).resolve().parents[2] / "scripts" / "live_m5_smoke.py"
    spec = importlib.util.spec_from_file_location("live_m5_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.__name__ != "__main__"
