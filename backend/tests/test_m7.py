"""Release guards and the production SPA. They do not call the network."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.providers.meta import ProviderResponseError
from app.services.m2_fixtures import CASE_MASS
from app.static_ui import _safe_file


class _Boom:
    def __init__(self) -> None:
        self.calls = 0

    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        del url, headers, body
        self.calls += 1
        raise ProviderResponseError("stopped before a live completion")


def test_stub_runs_when_live_is_disabled() -> None:
    client = TestClient(
        create_app(
            load_settings({"LIVE_RUNS_ENABLED": "false", "META_MODEL_ID": "muse-spark-1.3"}),
            live_transport=_Boom(),
        )
    )

    stub = client.post("/api/v1/run", json={"hypothesis": {"statement": CASE_MASS}})
    live = client.post(
        "/api/v1/run",
        json={"hypothesis": {"statement": CASE_MASS}, "mode": "live"},
    )

    assert stub.status_code == 200
    assert stub.json()["verdict"]["status"] == "NOT_YET_FALSIFIABLE"
    assert live.status_code == 403
    assert "Stub mode remains available" in live.json()["detail"]


def test_live_quota_stops_before_another_model_call() -> None:
    transport = _Boom()
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": "unit-test-not-a-secret",
                    "META_BASE_URL": "https://api.meta.ai/v1",
                    "META_MODEL_ID": "muse-spark-1.3",
                    "LIVE_RUN_LIMIT": "1",
                    "LIVE_RUN_WINDOW_SECONDS": "3600",
                }
            ),
            live_transport=transport,
        )
    )
    payload = {"hypothesis": {"statement": CASE_MASS}, "mode": "live"}

    first = client.post("/api/v1/run", json=payload)
    second = client.post("/api/v1/run", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert transport.calls == 1


def test_client_cannot_select_a_model_or_exceed_the_length() -> None:
    client = TestClient(
        create_app(load_settings({"MAX_HYPOTHESIS_LENGTH": "40"}))
    )

    extra = client.post(
        "/api/v1/run",
        json={
            "hypothesis": {"statement": "A short claim about period."},
            "meta_model_id": "other-model",
            "meta_base_url": "https://evil.example/v1",
        },
    )
    long = client.post(
        "/api/v1/run",
        json={"hypothesis": {"statement": "A" * 41}},
    )

    assert extra.status_code == 422
    assert long.status_code == 422


def test_oversized_body_is_refused() -> None:
    client = TestClient(create_app(load_settings({"MAX_REQUEST_BYTES": "1024"})))

    response = client.post(
        "/api/v1/run",
        json={"hypothesis": {"statement": "A" * 1500}},
    )

    assert response.status_code == 413


def test_spa_serves_the_ui_and_leaves_the_api_alone(tmp_path: Path) -> None:
    root = tmp_path / "dist"
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text("<title>FalsifyAI</title>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ui')", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("hidden", encoding="utf-8")
    client = TestClient(create_app(load_settings({}), static_dir=root))

    page = client.get("/")
    refresh = client.get("/demo")
    script = client.get("/assets/app.js")
    health = client.get("/health")
    examples = client.get("/api/v1/examples")
    missing = client.get("/api/v1/missing")

    assert page.status_code == 200
    assert "FalsifyAI" in page.text
    assert refresh.status_code == 200
    assert "FalsifyAI" in refresh.text
    assert script.text == "console.log('ui')"
    assert health.json()["milestone"] == "M7"
    assert examples.status_code == 200
    assert examples.json()["examples"][0]["example_id"] == "duffing"
    assert missing.status_code == 404
    assert _safe_file(root, "../secret.txt") is None
    assert "hidden" not in page.text
