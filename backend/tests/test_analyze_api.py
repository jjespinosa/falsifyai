"""API tests for the parser and critic. None of these open a socket."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.providers.meta import ProviderResponseError
from app.schemas.hypothesis import HypothesisInput
from app.services.fixtures import CASE_A, CASE_B, CASE_C
from app.services.modes import ExecutionMode
from app.services.parser import parse_hypothesis

_FAKE_KEY = "unit-test-not-a-secret"


class RecordingTransport:
    """Stands in for the Meta HTTP client and records the outgoing request."""

    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls: list[dict[str, object]] = []

    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        self.calls.append({"url": url, "headers": dict(headers), "body": body})
        if self.error is not None:
            raise self.error
        return {"choices": [{"message": {"content": self.content}}]}


class GuardTransport:
    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        del url, headers, body
        raise AssertionError("stub mode called the network transport")


def _client(settings: dict[str, str] | None = None, transport: object | None = None) -> TestClient:
    return TestClient(create_app(load_settings(settings or {}), live_transport=transport))


def test_empty_hypothesis_is_rejected() -> None:
    response = _client().post("/api/v1/analyze/parse", json={"statement": "   "})

    assert response.status_code == 422


def test_stub_parser_golden_cases_are_deterministic() -> None:
    client = _client(transport=GuardTransport())

    operational = client.post("/api/v1/analyze/parse", json={"statement": CASE_A})
    vague = client.post("/api/v1/analyze/parse", json={"statement": CASE_B})
    conventional = client.post("/api/v1/analyze/parse", json={"statement": CASE_C})

    assert operational.status_code == 200
    assert operational.json()["claims"][0]["is_operational"] is True
    assert operational.json()["claims"][0]["provenance"]["origin"] == "measured"
    assert vague.status_code == 200
    assert vague.json()["claims"][0]["is_operational"] is False
    assert vague.json()["undefined_terms"]
    assert conventional.status_code == 200
    assert [claim["claim_id"] for claim in conventional.json()["claims"]] == ["c1", "c2"]
    assert _FAKE_KEY not in operational.text


def test_stub_critic_golden_cases() -> None:
    client = _client(transport=GuardTransport())

    def critique(statement: str) -> dict:
        parsed = client.post("/api/v1/analyze/parse", json={"statement": statement})
        response = client.post(
            "/api/v1/analyze/critique",
            json={"hypothesis": {"statement": statement}, "parser_result": parsed.json()},
        )
        assert response.status_code == 200
        return response.json()

    pendulum = critique(CASE_A)
    vague = critique(CASE_B)
    plants = critique(CASE_C)

    assert pendulum["blocking_issues"] == []
    assert pendulum["minor_issues"][0]["category"] == "missing_control"
    assert vague["blocking_issues"]
    assert {issue["category"] for issue in vague["blocking_issues"]} >= {
        "undefined_variable",
        "non_operational_claim",
    }
    assert plants["conventional_explanations"]
    assert "vital energy" in plants["summary"].lower() or "vital-energy" in plants["summary"]


def test_non_operational_generic_claim_is_blocking() -> None:
    client = _client(transport=GuardTransport())
    statement = "The widget improves outcomes."

    parsed = client.post("/api/v1/analyze/parse", json={"statement": statement})
    critique = client.post(
        "/api/v1/analyze/critique",
        json={"hypothesis": {"statement": statement}, "parser_result": parsed.json()},
    )

    assert parsed.json()["claims"][0]["is_operational"] is False
    assert critique.status_code == 200
    assert critique.json()["blocking_issues"][0]["category"] == "non_operational_claim"


def test_default_mode_does_not_call_a_transport() -> None:
    transport = GuardTransport()
    response = _client(transport=transport).post(
        "/api/v1/analyze/parse",
        json={"statement": CASE_B},
    )

    assert response.status_code == 200
    assert response.json()["claims"][0]["provenance"]["origin"] == "assumed"
    assert response.json()["claims"][0]["epistemic_status"] == "speculative"


def test_live_mode_fails_without_a_key_and_does_not_call_out() -> None:
    transport = RecordingTransport(error=AssertionError("transport should not be used"))
    response = _client(
        {"META_BASE_URL": "https://api.meta.ai/v1", "META_MODEL_ID": "muse-spark-1.3"},
        transport,
    ).post("/api/v1/analyze/parse?mode=live", json={"statement": CASE_B})

    assert response.status_code == 503
    assert "MODEL_API_KEY" in response.json()["detail"]
    assert _FAKE_KEY not in response.text
    assert transport.calls == []


def test_live_mode_fails_without_a_model_id() -> None:
    transport = RecordingTransport(error=AssertionError("transport should not be used"))
    response = _client(
        {
            "MODEL_API_KEY": _FAKE_KEY,
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "",
        },
        transport,
    ).post("/api/v1/analyze/critique?mode=live", json=_critique_body(CASE_B))

    assert response.status_code == 503
    assert "META_MODEL_ID" in response.json()["detail"]
    assert _FAKE_KEY not in response.text
    assert transport.calls == []


def test_live_failure_does_not_fall_back_to_the_stub(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    transport = RecordingTransport(error=ProviderResponseError("live call failed"))
    response = _client(_live_settings(), transport).post(
        "/api/v1/analyze/parse?mode=live",
        json={"statement": CASE_A},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "live call failed"
    assert "claims" not in response.json()
    assert len(transport.calls) == 1
    assert _FAKE_KEY not in response.text
    assert _FAKE_KEY not in caplog.text
    assert _FAKE_KEY not in json.dumps(transport.calls[0]["body"])
    headers = transport.calls[0]["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == f"Bearer {_FAKE_KEY}"
    assert transport.calls[0]["url"] == "https://api.meta.ai/v1/chat/completions"
    body = transport.calls[0]["body"]
    assert isinstance(body, dict)
    assert body["model"] == "muse-spark-1.3"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["reasoning_effort"] == "minimal"


def test_live_structured_response_is_parsed_when_the_transport_is_fake() -> None:
    stub = parse_hypothesis(
        HypothesisInput(statement=CASE_B),
        mode=ExecutionMode.STUB,
        settings=load_settings({}),
    )
    transport = RecordingTransport(content=stub.model_dump_json())
    response = _client(_live_settings(), transport).post(
        "/api/v1/analyze/parse?mode=live",
        json={"statement": CASE_B},
    )

    assert response.status_code == 200
    assert response.json()["claims"][0]["is_operational"] is False
    assert _FAKE_KEY not in response.text


def test_critic_live_call_defaults_reasoning_effort_to_low() -> None:
    transport = RecordingTransport(error=ProviderResponseError("live call failed"))
    client = _client(_live_settings(), transport)

    default = client.post(
        "/api/v1/analyze/critique?mode=live",
        json=_critique_body(CASE_B),
    )

    assert default.status_code == 502
    assert transport.calls[0]["body"]["reasoning_effort"] == "low"
    transport.calls.clear()

    refused = client.post(
        "/api/v1/analyze/critique?mode=live&reasoning_effort=none",
        json=_critique_body(CASE_B),
    )

    assert refused.status_code == 422
    assert transport.calls == []

    sent = client.post(
        "/api/v1/analyze/critique?mode=live&reasoning_effort=high",
        json=_critique_body(CASE_B),
    )

    assert sent.status_code == 502
    assert transport.calls[0]["body"]["reasoning_effort"] == "high"


def test_responses_and_logs_omit_the_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client = _client(_live_settings(), GuardTransport())
    response = client.post("/api/v1/analyze/parse", json={"statement": CASE_A})

    assert response.status_code == 200
    assert _FAKE_KEY not in response.text
    assert _FAKE_KEY not in caplog.text


def _live_settings() -> dict[str, str]:
    return {
        "MODEL_API_KEY": _FAKE_KEY,
        "META_BASE_URL": "https://api.meta.ai/v1",
        "META_MODEL_ID": "muse-spark-1.3",
    }


def _critique_body(statement: str) -> dict:
    parsed = parse_hypothesis(
        HypothesisInput(statement=statement),
        mode=ExecutionMode.STUB,
        settings=load_settings({}),
    )
    return {
        "hypothesis": {"statement": statement},
        "parser_result": parsed.model_dump(mode="json"),
    }
