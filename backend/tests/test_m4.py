"""Experiment designer and falsification judge. None of these open a socket."""

import json
import math

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import load_settings
from app.main import create_app
from app.prompts.experiment import EXPERIMENT_SYSTEM_PROMPT
from app.prompts.judge import JUDGE_SYSTEM_PROMPT
from app.providers.meta import ProviderResponseError
from app.providers.schema_json import strict_json_schema, strict_subset_issues
from app.schemas.experiment import SAFETY_NOTE, ExperimentPlan, ExperimentPlanResult
from app.schemas.hypothesis import HypothesisInput
from app.schemas.identifiers import EXPERIMENT_ID_PATTERN
from app.schemas.verdict import FalsificationVerdict
from app.services.experiment import design_experiment
from app.services.judge import judge_hypothesis
from app.services.m3_fixtures import case_mass_plan
from app.services.m4_fixtures import (
    CASE_QUANT,
    NEXT_QUANTITATIVE_DEFINITION,
    blocked_context,
    identical_context,
    low_sensitivity_context,
    pendulum_context,
    pendulum_verdict,
    quantitative_context,
    quantitative_verdict,
)
from app.services.modes import ExecutionMode

_FAKE_KEY = "unit-test-not-a-secret"
_TRUTH_FIELDS = ("probability", "p_true", "posterior", "support_score", "confidence")


class GuardTransport:
    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        del url, headers, body
        raise AssertionError("stub mode called the network transport")


class RecordingTransport:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        self.calls.append({"body": body})
        raise self.error


def _has_truth_field(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in _TRUTH_FIELDS or _has_truth_field(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_truth_field(item) for item in value)
    return False


def _design(ctx):
    return design_experiment(
        ctx.hypothesis,
        ctx.parser_result,
        ctx.critique,
        ctx.null_model,
        ctx.observables,
        ctx.simulation_plan,
        None,
        mode=ExecutionMode.STUB,
        settings=load_settings({}),
        transport=GuardTransport(),
    )


def _judge(ctx, experiment=None, capability="context"):
    chosen = ctx.capability if capability == "context" else capability
    return judge_hypothesis(
        ctx.hypothesis,
        ctx.parser_result,
        ctx.critique,
        ctx.null_model,
        ctx.observables,
        ctx.simulation_plan,
        None,
        experiment if experiment is not None else ctx.experiment,
        chosen,
        mode=ExecutionMode.STUB,
        settings=load_settings({}),
        transport=GuardTransport(),
    )


def _body(ctx, **extra):
    payload = {
        "hypothesis": ctx.hypothesis.model_dump(mode="json"),
        "parser_result": ctx.parser_result.model_dump(mode="json"),
        "critique_report": ctx.critique.model_dump(mode="json"),
        "null_model_result": ctx.null_model.model_dump(mode="json"),
        "observable_design": ctx.observables.model_dump(mode="json"),
        "simulation_plan": ctx.simulation_plan.model_dump(mode="json"),
        "simulation_result": None,
    }
    payload.update(extra)
    return payload


def test_experiment_and_verdict_schemas_are_closed() -> None:
    for model in (ExperimentPlanResult, FalsificationVerdict):
        schema = strict_json_schema(model)
        rendered = json.dumps(schema)
        assert strict_subset_issues(schema) == []
        assert _has_truth_field(schema["properties"]) is False
        assert "validated" not in rendered
    assert EXPERIMENT_ID_PATTERN in json.dumps(strict_json_schema(ExperimentPlan))
    assert "You are the Experiment Designer inside FalsifyAI." in EXPERIMENT_SYSTEM_PROMPT
    assert "You are the Falsification Judge inside FalsifyAI." in JUDGE_SYSTEM_PROMPT
    with pytest.raises(ValidationError):
        FalsificationVerdict.model_validate(pendulum_verdict().model_dump() | {"status": "SUPPORTED"})
    with pytest.raises(ValidationError):
        FalsificationVerdict.model_validate(pendulum_verdict().model_dump() | {"p_true": 0.5})


def test_experiment_statuses_resolution_and_controls() -> None:
    pendulum = _design(pendulum_context())
    ready = _design(quantitative_context())
    blocked = _design(blocked_context())

    assert pendulum.status == "partial"
    assert pendulum.experiment is not None
    assert pendulum.experiment.required_resolution.status == "undefined"
    assert pendulum.experiment.required_resolution.value is None
    assert "effective length" in [item.name for item in pendulum.experiment.controlled_variables]
    assert SAFETY_NOTE in pendulum.experiment.safety_notes
    assert ready.status == "ready"
    assert ready.experiment is not None
    assert ready.experiment.required_resolution.status == "defined"
    assert ready.experiment.required_resolution.value == pytest.approx(0.1)
    assert blocked.status == "blocked"
    assert blocked.experiment is None
    payload = pendulum.experiment.model_dump()
    payload["experiment_id"] = "EXP1"
    with pytest.raises(ValidationError):
        ExperimentPlan.model_validate(payload)
    payload["experiment_id"] = "exp0"
    with pytest.raises(ValidationError):
        ExperimentPlan.model_validate(payload)
    bare = pendulum.experiment.model_dump()
    bare["safety_notes"] = ["Proceed without a human."]
    with pytest.raises(ValidationError, match="autonomous physical execution"):
        ExperimentPlan.model_validate(bare)


def test_reference_and_status_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import m4_fixtures
    from app.services.fixtures import normalize_statement
    from app.services.m2_fixtures import CASE_MASS

    def bad_claim():
        result = pendulum_context().experiment
        plan = result.experiment.model_copy(update={"target_claim_ids": ["c9"]})
        return result.model_copy(update={"experiment": plan})

    def bad_observable():
        result = pendulum_context().experiment
        plan = result.experiment.model_dump()
        plan["observable_ids"] = ["o9"]
        plan["required_resolution"]["observable_id"] = "o9"
        return ExperimentPlanResult.model_validate(result.model_dump() | {"experiment": plan})

    monkeypatch.setitem(m4_fixtures.GOLDEN_EXPERIMENTS, normalize_statement(CASE_MASS), bad_claim)
    with pytest.raises(ProviderResponseError, match="target_claim_ids"):
        _design(pendulum_context())
    monkeypatch.setitem(m4_fixtures.GOLDEN_EXPERIMENTS, normalize_statement(CASE_MASS), bad_observable)
    with pytest.raises(ProviderResponseError, match="observable_ids"):
        _design(pendulum_context())


def test_four_verdict_classes_and_rejected_combinations() -> None:
    pendulum = _judge(pendulum_context())
    testable = _judge(quantitative_context())
    coarse = _judge(low_sensitivity_context())
    same = _judge(identical_context())

    assert pendulum.status == "NOT_YET_FALSIFIABLE"
    assert pendulum.required_next_definition == NEXT_QUANTITATIVE_DEFINITION
    assert pendulum.delta_over_sigma is None
    assert testable.status == "TESTABLE"
    assert testable.delta_over_sigma == pytest.approx(100)
    assert coarse.status == "BELOW_SENSITIVITY"
    assert coarse.delta_over_sigma == pytest.approx(0.001)
    assert same.status == "NON_DISCRIMINATING"
    assert same.delta_over_sigma is None
    for verdict in (pendulum, testable, coarse, same):
        rendered = verdict.model_dump_json()
        assert "validated" not in rendered
        assert "supported" not in rendered
        assert _has_truth_field(verdict.model_dump()) is False

    from app.services import m4_fixtures
    from app.services.fixtures import normalize_statement
    from app.services.m2_fixtures import CASE_MASS

    def forced_testable():
        payload = quantitative_verdict().model_dump()
        payload["evidence_refs"] = ["c1", "h0", "o1", "exp1"]
        return FalsificationVerdict.model_validate(payload)

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setitem(m4_fixtures.GOLDEN_VERDICTS, normalize_statement(CASE_MASS), forced_testable)
        with pytest.raises(ProviderResponseError, match="defined resolution"):
            _judge(pendulum_context())
        quant = quantitative_context()
        quant.simulation_plan = case_mass_plan()
        monkeypatch.setitem(
            m4_fixtures.GOLDEN_VERDICTS, normalize_statement(CASE_QUANT), forced_testable
        )
        with pytest.raises(ProviderResponseError, match="quantitative discrimination"):
            _judge(quant)
        with pytest.raises(ProviderResponseError, match="explicit capability"):
            _judge(low_sensitivity_context(), capability=None)
    finally:
        monkeypatch.undo()


def test_unknown_evidence_ref_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import m4_fixtures
    from app.services.fixtures import normalize_statement

    def bad():
        payload = pendulum_verdict().model_dump()
        payload["evidence_refs"] = ["c1", "sim9"]
        return FalsificationVerdict.model_validate(payload)

    monkeypatch.setitem(
        m4_fixtures.GOLDEN_VERDICTS,
        normalize_statement(pendulum_context().hypothesis.statement),
        bad,
    )
    with pytest.raises(ProviderResponseError, match="evidence_refs"):
        _judge(pendulum_context())


def test_hazardous_request_has_no_procedure() -> None:
    ctx = pendulum_context()
    ctx.hypothesis = HypothesisInput(statement="Enrich uranium and record a period.")
    result = _design(ctx)

    assert result.status == "blocked"
    assert result.experiment is None
    assert "Hazardous procedure details are not generated." in result.blocking_missing_definitions[0]


def test_experiment_and_judge_routes_stay_local_by_default() -> None:
    ctx = pendulum_context()
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
    experiment = client.post("/api/v1/analyze/experiment", json=_body(ctx))
    judge = client.post(
        "/api/v1/analyze/judge",
        json=_body(ctx, experiment_plan=experiment.json(), capability=None),
    )

    assert experiment.status_code == 200
    assert experiment.json()["status"] == "partial"
    assert judge.status_code == 200
    assert judge.json()["status"] == "NOT_YET_FALSIFIABLE"
    assert judge.json()["delta_over_sigma"] is None
    assert _FAKE_KEY not in experiment.text
    assert _FAKE_KEY not in judge.text
    assert math.isfinite(float("nan")) is False


def test_live_judge_uses_medium_effort_and_does_not_fall_back() -> None:
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
    ctx = pendulum_context()
    response = client.post(
        "/api/v1/analyze/judge?mode=live",
        json=_body(
            ctx,
            experiment_plan=ctx.experiment.model_dump(mode="json"),
            capability=None,
        ),
    )

    assert response.status_code == 502
    assert transport.calls[0]["body"]["reasoning_effort"] == "medium"
    assert _FAKE_KEY not in json.dumps(transport.calls[0]["body"])
    refused = client.post(
        "/api/v1/analyze/judge?mode=live&reasoning_effort=none",
        json=_body(
            ctx,
            experiment_plan=ctx.experiment.model_dump(mode="json"),
            capability=None,
        ),
    )
    assert refused.status_code == 422
    assert len(transport.calls) == 1
