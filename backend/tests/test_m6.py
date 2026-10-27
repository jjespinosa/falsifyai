"""M6 generalization fixtures. They do not call the network."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

from app.config import load_settings
from app.schemas.hypothesis import HypothesisInput
from app.schemas.run import RunRequest
from app.services.grounding import number_is_stated
from app.services.m6_fixtures import CASE_DQ12, CASE_DUFFING, DQ12_NOTICE, DUFFING_NOTICE
from app.services.run import execute_run
from app.simulation.engine import run_simulation
from app.simulation.registry import FAMILIES

_ROOT = Path(__file__).resolve().parents[2]
_PIPELINE = (
    _ROOT / "backend" / "app" / "services" / "judge.py",
    _ROOT / "backend" / "app" / "services" / "run.py",
    _ROOT / "backend" / "app" / "services" / "experiment.py",
    _ROOT / "backend" / "app" / "services" / "observable.py",
    _ROOT / "backend" / "app" / "services" / "simulation_plan.py",
    _ROOT / "backend" / "app" / "services" / "null_model.py",
    _ROOT / "backend" / "app" / "services" / "parser.py",
    _ROOT / "backend" / "app" / "services" / "critic.py",
)
_FORBIDDEN_UI = (
    "new physics detected",
    "DQ-12 confirmed",
    "evidence of extra dimensions",
)
_INVENTED = ("Gamma_DQ", "L_DQ", "lambda", "0.075", "1.075")


def _run(statement: str):
    return execute_run(
        RunRequest(hypothesis=HypothesisInput(statement=statement)),
        settings=load_settings({}),
        run_id_factory=lambda: "run_m6demo01",
    )


def _stage(result, name: str) -> str:
    return next(item.status for item in result.stages if item.name == name)


def test_demo_metadata() -> None:
    from app.services.demo_fixtures import demo_examples

    cards = {item.example_id: item for item in demo_examples().examples}
    duffing = cards["duffing"]
    dq12 = cards["dq12"]

    assert duffing.title == "DUFFING CONTROL"
    assert duffing.label == "Synthetic quantitative control"
    assert duffing.purpose == "Shows quantitative end-to-end success."
    assert duffing.category == "SYNTHETIC CONTROL"
    assert duffing.notice == DUFFING_NOTICE
    assert duffing.statement == CASE_DUFFING
    assert dq12.title == "DQ-12 speculative stress test"
    assert dq12.label == "Speculative frontier stress test"
    assert dq12.purpose == "Shows adversarial refusal to overclaim."
    assert dq12.category == "FRONTIER STRESS TEST"
    assert dq12.notice == DQ12_NOTICE
    assert dq12.statement == CASE_DQ12


def test_duffing_statement_contains_every_supplied_number() -> None:
    for token in ("Omega(A) = 1", "0.075", "0 <= A <= 1", "0.01"):
        assert token in CASE_DUFFING


def test_duffing_local_numerics_and_testable_verdict() -> None:
    result = _run(CASE_DUFFING)
    spec = result.simulation_plan.spec
    curve = result.simulation_result
    assert spec is not None and curve is not None
    assert spec.h0.family in FAMILIES
    assert spec.h1.family in FAMILIES
    source = CASE_DUFFING
    for family in (spec.h0, spec.h1):
        for value in family.parameters.model_dump().values():
            if value is not None:
                assert number_is_stated(float(value), source)
    direct = run_simulation(spec)
    assert direct.x[0] == pytest.approx(0.0)
    assert direct.x[-1] == pytest.approx(1.0)
    assert direct.h0[0] == pytest.approx(1.0)
    assert direct.h0[-1] == pytest.approx(1.0)
    assert all(value == pytest.approx(1.0) for value in direct.h0)
    assert direct.h1[0] == pytest.approx(1.0)
    assert direct.h1[-1] == pytest.approx(1.075)
    for x_value, h1_value in zip(direct.x, direct.h1, strict=True):
        assert h1_value == pytest.approx(1.0 + 0.075 * x_value * x_value)
    assert direct.delta[0] == pytest.approx(0.0)
    assert direct.delta[-1] == pytest.approx(0.075)
    assert all(math.isfinite(value) for value in (*direct.h0, *direct.h1, *direct.delta))
    assert _stage(result, "simulation_plan") == "success"
    assert _stage(result, "simulation") == "success"
    assert result.experiment.status == "ready"
    assert result.experiment.experiment.required_resolution.status == "defined"
    assert result.experiment.experiment.required_resolution.value == pytest.approx(0.01)
    assert result.verdict.status == "TESTABLE"
    assert result.verdict.delta_over_sigma == pytest.approx(7.5)
    assert "probability" not in result.verdict.model_dump()
    assert result.usage.model_calls == 0


def test_dq12_does_not_invent_a_law_or_treat_a_residual_as_evidence() -> None:
    result = _run(CASE_DQ12)
    blob = result.model_dump_json()
    observable = result.observable_design.observables[0]

    assert result.parser.claims[0].is_operational is False
    assert result.null_model.models[0].can_mimic_claim is True
    assert "ordinary decoherence" in result.null_model.models[0].description.lower()
    assert observable.discriminating is False
    assert "not evidence" in observable.definition
    assert result.simulation_plan.status == "blocked"
    assert result.simulation_plan.spec is None
    assert result.simulation_result is None
    assert result.experiment.status == "partial"
    assert result.verdict.status == "NOT_YET_FALSIFIABLE"
    assert "twelve-dimensional separation" in result.verdict.required_next_definition
    assert "not evidence" in result.verdict.primary_reason
    for token in _INVENTED:
        assert token not in blob
    assert "d12 =" not in blob
    assert result.usage.model_calls == 0


def test_pipeline_has_no_name_specific_verdict_branch() -> None:
    for path in _PIPELINE:
        text = path.read_text(encoding="utf-8")
        assert "DQ-12" not in text
        assert "Duffing" not in text
    prompt_dir = _ROOT / "backend" / "app" / "prompts"
    for path in prompt_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "DQ-12" not in text
        assert "Duffing" not in text


def test_frontend_warnings_do_not_claim_discovery() -> None:
    root = _ROOT / "frontend" / "src"
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )
    for phrase in _FORBIDDEN_UI:
        assert phrase not in text
    assert DUFFING_NOTICE in text
    assert DQ12_NOTICE in text
    assert "FalsifyAI is testing DQ-12 adversarially." in text


def test_m6_smoke_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during smoke-script import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    path = _ROOT / "scripts" / "live_m6_smoke.py"
    spec = importlib.util.spec_from_file_location("live_m6_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.__name__ != "__main__"
    assert "duffing" in module.CASES
    assert "dq12" in module.CASES
