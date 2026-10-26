"""Tests for the M0 health check."""

from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app


def test_health_reports_m1() -> None:
    client = TestClient(create_app(load_settings({})))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "falsifyai",
        "milestone": "M1",
    }


def test_health_body_has_no_configuration() -> None:
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": "unit-test-not-a-secret",
                    "META_BASE_URL": "https://example.test/v1",
                    "META_MODEL_ID": "muse-spark-1.3",
                }
            )
        )
    )

    body = client.get("/health").text

    assert "unit-test-not-a-secret" not in body
    assert "example.test" not in body
    assert "muse-spark" not in body
