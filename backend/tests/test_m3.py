"""Simulation planner and restricted simulator tests. None of these open a socket."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import load_settings
from app.main import create_app
from app.prompts.simulation import SIMULATION_SYSTEM_PROMPT
from app.providers.meta import ProviderResponseError
from app.providers.schema_json import strict_json_schema, strict_subset_issues
from app.schemas.hypothesis import HypothesisInput
from app.schemas.identifiers import SIMULATION_ID_PATTERN
from app.schemas.observable import ObservableDesignResult
from app.schemas.simulation import (
    SimulationPlanResult,
    SimulationResult,
    SimulationSpec,
)
from app.services.fixtures import CASE_B, case_b_critic, case_b_parser
from app.services.m2_fixtures import CASE_MASS, case_b_null, case_mass_observable
from app.services.m3_fixtures import (
    QUANTITATIVE_H1_BLOCKER,
    SYNTHETIC_CURVE,
    family_parameters,
    synthetic_plan,
    synthetic_spec,
)
from app.services.modes import ExecutionMode
from app.services.simulation_plan import plan_simulation
from app.simulation.engine import SimulationRejected, run_simulation
from app.simulation.limits import require_evaluation_budget
from app.simulation.registry import active_parameters, evaluate

_FAKE_KEY = "unit-test-not-a-secret"
_FORBIDDEN_FIELDS = ("verdict", "falsified", "p_value", "significance", "not_yet_falsifiable")


class GuardTransport:
    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        del url, headers, body
        raise AssertionError("this route called the network transport")


class RecordingTransport:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        self.calls.append({"url": url, "headers": dict(headers), "body": body})
        raise self.error


def _has_forbidden_field(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in _FORBIDDEN_FIELDS or _has_forbidden_field(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_forbidden_field(item) for item in value)
    return False


def _bundle(statement: str, design: ObservableDesignResult | None = None) -> dict[str, object]:
    hypothesis = HypothesisInput(statement=statement)
    return {
        "hypothesis": hypothesis,
        "parser_result": case_b_parser(HypothesisInput(statement=CASE_B)),
        "critique_report": case_b_critic(),
        "null_model_result": case_b_null(),
        "observable_design": design if design is not None else case_mass_observable(),
    }


def _plan(statement: str, design: ObservableDesignResult | None = None) -> SimulationPlanResult:
    bundle = _bundle(statement, design)
    return plan_simulation(
        bundle["hypothesis"],  # type: ignore[arg-type]
        bundle["parser_result"],  # type: ignore[arg-type]
        bundle["critique_report"],  # type: ignore[arg-type]
        bundle["null_model_result"],  # type: ignore[arg-type]
        bundle["observable_design"],  # type: ignore[arg-type]
        mode=ExecutionMode.STUB,
        settings=load_settings({}),
        transport=GuardTransport(),
    )


def test_plan_schemas_fit_strict_output_and_have_no_code_field() -> None:
    for model in (SimulationPlanResult, SimulationSpec, SimulationResult):
        schema = strict_json_schema(model)
        rendered = json.dumps(schema)
        assert strict_subset_issues(schema) == []
        assert "$ref" not in rendered
        assert "NOT_YET_FALSIFIABLE" not in rendered
        assert _has_forbidden_field(schema["properties"]) is False
        assert "code" not in schema["properties"]
        assert "python" not in schema["properties"]
    assert SIMULATION_ID_PATTERN in json.dumps(strict_json_schema(SimulationSpec))
    assert "You are the Simulation Planner inside FalsifyAI." in SIMULATION_SYSTEM_PROMPT
    assert "Never return Python code." in SIMULATION_SYSTEM_PROMPT


def test_ready_and_blocked_plan_shapes() -> None:
    ready = synthetic_plan()
    blocked = _plan(CASE_MASS)

    assert ready.status == "ready"
    assert ready.spec is not None
    assert ready.blocking_missing_definitions == []
    served = _plan(SYNTHETIC_CURVE)
    assert served.status == "ready"
    assert served.spec is not None
    assert blocked.status == "blocked"
    assert blocked.spec is None
    assert QUANTITATIVE_H1_BLOCKER in blocked.blocking_missing_definitions
    with pytest.raises(ValidationError, match="blocked plan must not include a spec"):
        SimulationPlanResult.model_validate(ready.model_dump() | {"status": "blocked"})


def test_canonical_simulation_id_and_spec_rejects_code() -> None:
    payload = synthetic_spec().model_dump()
    assert payload["simulation_id"] == "sim1"
    payload["simulation_id"] = "SIM1"
    with pytest.raises(ValidationError):
        SimulationSpec.model_validate(payload)
    payload["simulation_id"] = "sim0"
    with pytest.raises(ValidationError):
        SimulationSpec.model_validate(payload)
    payload = synthetic_spec().model_dump()
    payload["code"] = "x = 1"
    with pytest.raises(ValidationError):
        SimulationSpec.model_validate(payload)


def test_family_parameters_reject_unknown_missing_extra_and_non_finite() -> None:
    with pytest.raises(ValidationError):
        SimulationSpec.model_validate(
            synthetic_spec().model_dump() | {"h0": {"family": "sine", "parameters": family_parameters(value=1).model_dump()}}
        )
    with pytest.raises(ValueError, match="missing family parameter"):
        active_parameters("linear", {"slope": 2.0, "intercept": None})
    with pytest.raises(ValidationError, match="extra family parameter"):
        SimulationSpec.model_validate(
            _with_h0(family_parameters(slope=2, intercept=1, quadratic=0.5))
        )
    with pytest.raises(ValueError, match="unknown model family"):
        active_parameters("sine", {"value": 1.0})
    with pytest.raises(ValidationError, match="finite"):
        family_parameters(slope=math.inf, intercept=1)


def test_grid_bounds() -> None:
    payload = synthetic_spec().model_dump()
    payload["independent_variable"]["max"] = -1
    with pytest.raises(ValidationError, match="invalid grid"):
        SimulationSpec.model_validate(payload)
    payload = synthetic_spec().model_dump()
    payload["independent_variable"]["points"] = 0
    with pytest.raises(ValidationError):
        SimulationSpec.model_validate(payload)
    payload = synthetic_spec().model_dump()
    payload["independent_variable"]["points"] = 1001
    with pytest.raises(ValidationError):
        SimulationSpec.model_validate(payload)
    with pytest.raises(ValueError, match="total evaluations"):
        require_evaluation_budget(1000, 101)


def test_registered_families_and_synthetic_delta() -> None:
    grid = np.linspace(0, 2, 3)
    assert np.allclose(evaluate("constant", {"value": 4.0}, grid), [4, 4, 4])
    assert np.allclose(evaluate("linear", {"slope": 2.0, "intercept": 1.0}, grid), [1, 3, 5])
    assert np.allclose(
        evaluate("quadratic", {"quadratic": 0.1, "slope": 2.0, "intercept": 1.0}, np.array([0.0, 10.0])),
        [1, 31],
    )
    assert np.allclose(
        evaluate("exponential_decay", {"amplitude": 3.0, "rate": 0.0, "offset": 1.0}, grid),
        [4, 4, 4],
    )
    first = run_simulation(synthetic_spec())
    second = run_simulation(synthetic_spec())
    assert first.model_dump() == second.model_dump()
    assert len(first.x) == len(first.h0) == len(first.h1) == len(first.delta) == 11
    expected = [0.1 * value * value for value in first.x]
    assert first.delta == pytest.approx(expected)
    assert first.h0[0] == pytest.approx(1)
    assert first.h0[-1] == pytest.approx(21)
    assert first.h1[-1] == pytest.approx(31)
    overflowing = synthetic_spec().model_dump()
    overflowing["h1"] = {
        "family": "exponential_decay",
        "parameters": family_parameters(amplitude=1, rate=-80, offset=0).model_dump(),
    }
    with pytest.raises(SimulationRejected, match="finite"):
        run_simulation(SimulationSpec.model_validate(overflowing))


def test_parameter_sweep_changes_only_the_named_coefficient() -> None:
    spec = synthetic_spec().model_dump()
    spec["template"] = "parameter_sweep"
    spec["independent_variable"]["min"] = 10
    spec["independent_variable"]["max"] = 10
    spec["independent_variable"]["points"] = 1
    spec["sweep"] = {
        "target": "h1",
        "parameter": "quadratic",
        "min": 0,
        "max": 0.2,
        "points": 3,
    }
    result = run_simulation(SimulationSpec.model_validate(spec))

    assert result.x == pytest.approx([0, 0.1, 0.2])
    assert result.h0 == pytest.approx([21, 21, 21])
    assert result.delta == pytest.approx([0, 10, 20])


def test_mass_plan_stays_blocked_and_an_invented_curve_is_not_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import m3_fixtures
    from app.services.fixtures import normalize_statement

    blocked = _plan(CASE_MASS)
    assert blocked.status == "blocked"
    assert blocked.spec is None
    monkeypatch.setitem(m3_fixtures.GOLDEN_PLANS, normalize_statement(CASE_MASS), synthetic_plan)
    rewritten = _plan(CASE_MASS)
    assert rewritten.status == "blocked"
    assert rewritten.spec is None
    assert rewritten.blocking_missing_definitions


def test_unknown_observable_reference_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import m3_fixtures
    from app.services.fixtures import normalize_statement

    def bad() -> SimulationPlanResult:
        plan = synthetic_plan()
        spec = plan.spec
        assert spec is not None
        updated = spec.model_copy(update={"observable_id": "o9"})
        return plan.model_copy(update={"observable_id": "o9", "spec": updated})

    monkeypatch.setitem(m3_fixtures.GOLDEN_PLANS, normalize_statement(SYNTHETIC_CURVE), bad)
    with pytest.raises(ProviderResponseError, match="observable_id"):
        _plan(SYNTHETIC_CURVE)


def test_non_discriminating_observable_blocks_a_ready_spec() -> None:
    design = case_mass_observable()
    candidate = design.observables[0].model_dump()
    candidate["discriminating"] = False
    candidate["predicted_difference"] = "unknown"
    quiet = ObservableDesignResult.model_validate(
        design.model_dump() | {"observables": [candidate]}
    )
    result = _plan(SYNTHETIC_CURVE, quiet)

    assert result.status == "blocked"
    assert result.spec is None


def test_simulation_routes_keep_the_model_out_of_local_execution() -> None:
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": _FAKE_KEY,
                    "META_BASE_URL": "https://example.test/v1",
                    "META_MODEL_ID": "muse-spark-1.3",
                }
            ),
            live_transport=GuardTransport(),
        )
    )
    bundle = _bundle(CASE_MASS)
    plan_response = client.post(
        "/api/v1/analyze/simulation-plan",
        json={key: value.model_dump(mode="json") for key, value in bundle.items()},
    )
    simulate_response = client.post(
        "/api/v1/simulate",
        json=synthetic_spec().model_dump(mode="json"),
    )

    assert plan_response.status_code == 200
    assert plan_response.json()["status"] == "blocked"
    assert plan_response.json()["spec"] is None
    assert simulate_response.status_code == 200
    body = simulate_response.json()
    assert body["simulation_id"] == "sim1"
    assert len(body["x"]) == len(body["delta"])
    assert _FAKE_KEY not in plan_response.text
    assert _FAKE_KEY not in simulate_response.text
    assert _has_forbidden_field(plan_response.json()) is False
    assert _has_forbidden_field(body) is False


def test_live_planner_uses_medium_effort_and_does_not_fall_back() -> None:
    transport = RecordingTransport(error=ProviderResponseError("live call failed"))
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": _FAKE_KEY,
                    "META_BASE_URL": "https://api.meta.ai/v1",
                    "META_MODEL_ID": "muse-spark-1.3",
                }
            ),
            live_transport=transport,
        )
    )
    bundle = _bundle(CASE_MASS)
    response = client.post(
        "/api/v1/analyze/simulation-plan?mode=live",
        json={key: value.model_dump(mode="json") for key, value in bundle.items()},
    )

    assert response.status_code == 502
    assert "status" not in response.json()
    body = transport.calls[0]["body"]
    assert body["reasoning_effort"] == "medium"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert _FAKE_KEY not in json.dumps(body)
    refused = client.post(
        "/api/v1/analyze/simulation-plan?mode=live&reasoning_effort=none",
        json={key: value.model_dump(mode="json") for key, value in bundle.items()},
    )
    assert refused.status_code == 422
    assert len(transport.calls) == 1
    local = client.post("/api/v1/simulate", json=synthetic_spec().model_dump(mode="json"))
    assert local.status_code == 200
    assert len(transport.calls) == 1


def test_simulator_source_does_not_execute_model_text() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    for relative in (
        "simulation/engine.py",
        "simulation/registry.py",
        "schemas/simulation.py",
        "services/simulation_plan.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "eval(" not in text
        assert "exec(" not in text
        assert "compile(" not in text


def _with_h0(parameters) -> dict[str, object]:
    payload = synthetic_spec().model_dump()
    payload["h0"] = {"family": "linear", "parameters": parameters.model_dump()}
    return payload
