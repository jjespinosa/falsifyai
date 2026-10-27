"""End-to-end run orchestration. These tests do not call the network."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import DEV_CORS_ORIGINS, create_app
from app.providers.meta import ProviderResponseError
from app.schemas.hypothesis import HypothesisInput
from app.schemas.run import RunRequest
from app.services.demo_fixtures import SYNTHETIC_NOTICE, VAGUE_FIELD
from app.services.m2_fixtures import CASE_MASS
from app.services.m4_fixtures import CASE_QUANT
from app.services.reasoning import stage_effort
from app.services.run import UsageTransport, _usage, execute_run

_SECRET = "LLM_run_test_secret"


def _request(statement: str) -> RunRequest:
    return RunRequest(hypothesis=HypothesisInput(statement=statement))


def _run(statement: str):
    return execute_run(
        _request(statement),
        settings=load_settings({}),
        run_id_factory=lambda: "run_stub0001",
    )


def test_reasoning_profiles_stay_at_or_below_medium() -> None:
    for profile in ("economy", "balanced"):
        efforts = [
            stage_effort(profile, name)
            for name in (
                "parser",
                "critic",
                "null_model",
                "observable",
                "simulation_plan",
                "experiment",
                "judge",
            )
        ]
        assert "high" not in efforts
        assert "xhigh" not in efforts
        assert "max" not in efforts
    assert stage_effort("economy", "null_model") == "low"
    assert stage_effort("balanced", "experiment") == "medium"
    assert stage_effort("economy", "parser") == "minimal"


def test_run_request_defaults_to_stub_economy() -> None:
    request = RunRequest(hypothesis=HypothesisInput(statement="A claim."))

    assert request.mode.value == "stub"
    assert request.reasoning_profile == "economy"


def test_pendulum_stub_is_scientifically_blocked_and_skips_simulation() -> None:
    result = _run(CASE_MASS)

    assert result.status == "scientifically_blocked"
    assert result.summary is not None
    assert result.summary.verdict == "NOT_YET_FALSIFIABLE"
    assert result.summary.observable
    assert result.summary.required_next_definition
    assert result.simulation_plan is not None
    assert result.simulation_plan.status == "blocked"
    assert result.simulation_result is None
    assert _status(result, "simulation") == "skipped"
    assert _status(result, "simulation_plan") == "blocked"
    assert _status(result, "experiment") == "success"
    assert result.experiment is not None
    assert result.experiment.status == "partial"
    assert result.usage.model_calls == 0
    assert result.usage.total_tokens == 0
    assert result.error is None


def test_vague_claim_has_no_observable_and_is_not_a_system_failure() -> None:
    result = _run(VAGUE_FIELD)

    assert result.status == "scientifically_blocked"
    assert _status(result, "observable") == "blocked"
    assert _status(result, "observable") != "failed"
    assert result.observable_design is not None
    assert result.observable_design.observables == []
    assert result.experiment is not None
    assert result.experiment.status == "blocked"
    assert result.verdict is not None
    assert result.verdict.status == "NOT_YET_FALSIFIABLE"
    assert result.error is None


def test_synthetic_stub_reaches_testable_with_a_local_curve() -> None:
    result = _run(CASE_QUANT)

    assert result.status == "completed"
    assert result.summary is not None
    assert result.summary.verdict == "TESTABLE"
    assert result.summary.simulation_status == "ready"
    assert "Synthetic" in (result.summary.primary_reason + result.hypothesis_text)
    assert result.simulation_result is not None
    assert len(result.simulation_result.x) == len(result.simulation_result.h0)
    assert len(result.simulation_result.h1) == len(result.simulation_result.delta)
    assert _status(result, "simulation") == "success"
    assert result.usage.model_calls == 0


def test_system_failure_stops_the_pipeline_and_redacts_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args, **kwargs):
        raise ProviderResponseError(f"transport said {_SECRET}")

    monkeypatch.setattr("app.services.run.parse_hypothesis", broken)
    result = execute_run(
        _request("A claim that fails before any science."),
        settings=load_settings({"MODEL_API_KEY": _SECRET}),
        run_id_factory=lambda: "run_failed01",
    )

    assert result.status == "failed"
    assert _status(result, "parser") == "failed"
    assert _status(result, "judge") == "skipped"
    assert result.summary is None
    assert result.verdict is None
    assert result.error is not None
    assert _SECRET not in result.model_dump_json()
    assert result.usage.model_calls == 0


def test_usage_meter_sums_live_calls_without_reasoning_text() -> None:
    class Inner:
        def __init__(self) -> None:
            self.last_usage = None

        def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]):
            self.last_usage = {
                "prompt_tokens": 2,
                "completion_tokens": 5,
                "reasoning_tokens": 3,
                "total_tokens": 7,
            }
            return {"ok": True}

    meter = UsageTransport(Inner())
    meter.post_json(url="https://api.meta.ai/v1/chat/completions", headers={}, body={})
    meter.post_json(url="https://api.meta.ai/v1/chat/completions", headers={}, body={})
    usage = _usage(meter, 12)

    assert usage.model_calls == 2
    assert usage.prompt_tokens == 4
    assert usage.completion_tokens == 10
    assert usage.reasoning_tokens == 6
    assert usage.total_tokens == 14
    assert "reasoning" not in usage.model_dump_json() or usage.reasoning_tokens == 6


def test_examples_and_stub_run_endpoint_hide_secrets() -> None:
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": _SECRET,
                    "META_BASE_URL": "https://api.meta.ai/v1",
                    "META_MODEL_ID": "muse-spark-1.3",
                }
            )
        )
    )

    examples = client.get("/api/v1/examples", headers={"Origin": "http://localhost:5173"})
    run = client.post(
        "/api/v1/run",
        json={"hypothesis": {"statement": CASE_MASS}},
    )

    assert examples.status_code == 200
    body = examples.json()
    assert [item["example_id"] for item in body["examples"]] == [
        "duffing",
        "dq12",
        "pendulum",
        "synthetic",
        "vague_field",
    ]
    assert body["examples"][3]["notice"] == SYNTHETIC_NOTICE
    assert examples.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "*" not in examples.headers["access-control-allow-origin"]
    assert set(DEV_CORS_ORIGINS) == {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
    assert run.status_code == 200
    payload = run.json()
    assert payload["status"] == "scientifically_blocked"
    assert payload["verdict"]["status"] == "NOT_YET_FALSIFIABLE"
    assert payload["usage"]["model_calls"] == 0
    assert _SECRET not in run.text
    assert _SECRET not in examples.text


def test_frontend_source_has_no_api_key() -> None:
    root = Path(__file__).resolve().parents[2] / "frontend"
    files = [root / "index.html", *root.joinpath("src").rglob("*")]
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in files
        if path.is_file() and path.suffix in {".ts", ".tsx", ".css", ".html"}
    )

    assert _SECRET not in text
    assert "Bearer " not in text
    assert "sk-" not in text


def _status(result, name: str) -> str:
    return next(item.status for item in result.stages if item.name == name)
