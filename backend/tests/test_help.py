"""Tests for milestone help and the generated API reference."""

from fastapi.testclient import TestClient

from app.config import load_settings
from app.help import help_document
from app.main import create_app

_FAKE_KEY = "unit-test-not-a-secret"


def test_help_describes_the_shell_without_runtime_configuration() -> None:
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": _FAKE_KEY,
                    "META_BASE_URL": "https://example.test/v1",
                    "META_MODEL_ID": "other-model",
                }
            )
        )
    )

    response = client.get("/help")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "falsifyai"
    assert body["milestone"] == "M4"
    assert "/health" in [item["path"] for item in body["endpoints"]]
    assert "/help" in [item["path"] for item in body["endpoints"]]
    assert "docs/m0.md" in [item["location"] for item in body["documentation"]]
    assert "HypothesisInput" in [item["name"] for item in body["contracts"]]
    assert "ScientificClaim" in [item["name"] for item in body["contracts"]]
    assert "muse-spark-1.3" in response.text
    assert "other-model" not in response.text
    assert "example.test" not in response.text
    assert _FAKE_KEY not in response.text


def test_help_document_does_not_read_settings() -> None:
    document = help_document()

    assert document.milestone == "M4"
    rendered = document.model_dump_json()
    assert "MODEL_API_KEY" in rendered
    assert _FAKE_KEY not in rendered


def test_openapi_lists_health_and_help() -> None:
    client = TestClient(create_app(load_settings({})))

    response = client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "FalsifyAI"
    assert "/health" in spec["paths"]
    assert "/help" in spec["paths"]
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
