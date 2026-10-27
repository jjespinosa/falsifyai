"""Experiment diagnostics. These tests do not call the network."""

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.diagnostics.experiment_response import (
    compare_experiment_schemas,
    describe_validation_error,
    domain_rules,
    experiment_profile,
    message_content,
    render_experiment_profile,
    render_validation_errors,
    safe_metadata,
    semantic_rules,
    validator_index,
    write_experiment_response,
)
from app.diagnostics.m4_checkpoint import ReplayRefused, load_replay, select_replay, write_checkpoint
from app.prompts.experiment import EXPERIMENT_SYSTEM_PROMPT
from app.schemas.experiment import SAFETY_NOTE, ExperimentPlan, ExperimentPlanResult
from app.schemas.hypothesis import HypothesisInput
from app.services.experiment import _guard
from app.services.m2_fixtures import case_mass_observable
from app.services.m3_fixtures import case_mass_plan
from app.services.m4_fixtures import pendulum_context, pendulum_experiment, pendulum_verdict

_SECRET = "LLM_experiment_diagnostic_secret"


def test_intended_pendulum_experiment_validates_locally() -> None:
    observable = case_mass_observable()
    simulation = case_mass_plan()
    experiment = pendulum_experiment()
    verdict = pendulum_verdict()
    restored = ExperimentPlanResult.model_validate(json.loads(experiment.model_dump_json()))
    context = pendulum_context()

    assert observable.observables[0].observable_id == "o1"
    assert observable.observables[0].discriminating is True
    assert observable.observables[0].non_blocking_missing_definitions
    assert simulation.status == "blocked"
    assert simulation.spec is None
    assert restored.status == "partial"
    assert restored.experiment is not None
    assert restored.experiment.observable_ids == ["o1"]
    assert restored.experiment.required_resolution.status == "undefined"
    assert restored.experiment.required_resolution.value is None
    _guard(context.hypothesis, context.parser_result, context.observables, restored)
    assert verdict.status == "NOT_YET_FALSIFIABLE"
    assert verdict.delta_over_sigma is None
    assert verdict.required_next_definition


def test_safety_note_must_match_the_canonical_item_exactly() -> None:
    plan = pendulum_experiment().experiment
    assert plan is not None
    exact = ExperimentPlan.model_validate(plan.model_dump())
    dotted = plan.model_dump()
    dotted["safety_notes"] = [SAFETY_NOTE + "."]
    paraphrase = plan.model_dump()
    paraphrase["safety_notes"] = ["Do not execute this experiment autonomously"]
    prompt_lines = EXPERIMENT_SYSTEM_PROMPT.splitlines()

    assert exact.safety_notes == [SAFETY_NOTE]
    assert pendulum_experiment().status == "partial"
    with pytest.raises(ValidationError, match="safety_notes"):
        ExperimentPlan.model_validate(dotted)
    with pytest.raises(ValidationError, match="safety_notes"):
        ExperimentPlan.model_validate(paraphrase)
    assert SAFETY_NOTE in prompt_lines
    assert SAFETY_NOTE + "." not in EXPERIMENT_SYSTEM_PROMPT
    assert (
        "Do not add a period, colon, prefix, suffix, quotation mark, or any other character to that array item."
        in EXPERIMENT_SYSTEM_PROMPT
    )


def test_validation_report_keeps_every_error_and_redacts_the_value() -> None:
    payload = json.loads(pendulum_experiment().model_dump_json())
    payload["status"] = "PARTIAL"
    payload["experiment"]["experiment_id"] = _SECRET
    payload["experiment"]["required_resolution"]["value"] = "missing"
    with pytest.raises(ValidationError) as captured:
        ExperimentPlanResult.model_validate(payload)

    rendered = render_validation_errors(captured.value, secret=_SECRET)
    rows = describe_validation_error(captured.value, secret=_SECRET)
    paths = {row["path"] for row in rows}

    assert len(rows) >= 2
    assert "validation_errors:" in rendered
    assert "status" in paths
    assert "experiment.experiment_id" in paths
    assert "experiment.required_resolution.value" in paths
    assert all(row["type"] and row["message"] and row["value_type"] for row in rows)
    assert _SECRET not in rendered
    assert "[redacted]" in rendered


def test_experiment_profile_counts_the_partial_plan() -> None:
    payload = json.loads(pendulum_experiment().model_dump_json())
    raw = json.dumps(payload)
    profile = experiment_profile(payload, raw)
    rendered = render_experiment_profile(profile)

    assert profile["character_count"] == len(raw)
    assert profile["status"] == "partial"
    assert profile["experiment_is_null"] is False
    assert profile["blocker_count"] == 1
    assert profile["required_resolution_exists"] is True
    assert profile["required_resolution_status"] == "undefined"
    assert profile["required_resolution_value_type"] == "NoneType"
    assert profile["falsifier_candidate_exists"] is True
    assert profile["array_counts"]["controlled_variables"] == 6
    assert profile["array_counts"]["procedure_outline"] == 3
    assert "raw_chars:" in rendered
    assert "count_confounders: 4" in rendered


def test_saved_experiment_response_keeps_metadata_and_drops_secrets(tmp_path: Path) -> None:
    content = json.dumps({"status": "partial", "summary": _SECRET, "note": "Bearer super-secret-token"})
    body = {
        "model": "muse-spark-1.3",
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 5,
            "total_tokens": 8,
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
        "authorization": "Bearer should-not-be-copied",
    }
    destination = tmp_path / "live_experiment_response.json"
    write_experiment_response(
        destination,
        content,
        safe_metadata(body, http_status=200),
        secret=_SECRET,
    )
    saved = json.loads(destination.read_text(encoding="utf-8"))
    rendered = destination.read_text(encoding="utf-8")

    assert message_content(body) == content
    assert saved["metadata"]["http_status"] == 200
    assert saved["metadata"]["usage"]["reasoning_tokens"] == 2
    assert "authorization" not in saved["metadata"]
    assert _SECRET not in rendered
    assert "super-secret-token" not in rendered
    assert "should-not-be-copied" not in rendered


def test_schema_comparison_and_validator_catalog() -> None:
    report = compare_experiment_schemas()
    catalog = {(rule.model, rule.validator) for rule in semantic_rules()}

    assert report["sent_equals_transformed"] is True
    assert report["raw_ref_count"] > 0
    assert report["transformed_ref_count"] == 0
    assert catalog == validator_index()
    assert all(rule.in_json_schema is False for rule in semantic_rules())
    assert all(rule.in_json_schema is False for rule in domain_rules())
    assert any("required_resolution" in item and item.endswith("value") for item in report["sent_nullable"])
    assert any(item.endswith("experiment") for item in report["sent_nullable"])
    assert any("partial" in item for item in report["sent_enums"])
    status = next(rule for rule in semantic_rules() if rule.validator == "_status_matches_plan")
    resolution = next(rule for rule in semantic_rules() if rule.validator == "_value_matches_status")
    safety = next(rule for rule in semantic_rules() if rule.validator == "_plan_is_traceable")
    assert "partial" in status.rule
    assert "undefined" in resolution.rule
    assert "No autonomous physical execution" in safety.rule


def test_checkpoint_round_trip_redacts_and_replay_refuses_a_missing_experiment(tmp_path: Path) -> None:
    context = pendulum_context()
    hypothesis = HypothesisInput(
        statement="A measurable claim for the checkpoint.",
        context=f"Bearer super-secret-token {_SECRET}",
    )
    stages = {
        "hypothesis": hypothesis,
        "parser": context.parser_result,
        "critic": context.critique,
        "null": context.null_model,
        "observable": context.observables,
        "planner": context.simulation_plan,
    }
    path = tmp_path / "live_m4_checkpoint.json"
    last = write_checkpoint(path, stages, secret=_SECRET)
    saved = path.read_text(encoding="utf-8")
    selection = load_replay(path, "experiment")

    assert last == "planner"
    assert _SECRET not in saved
    assert "super-secret-token" not in saved
    assert selection.stage == "experiment"
    assert selection.experiment is None
    assert selection.simulation_plan.status == "blocked"
    with pytest.raises(ReplayRefused, match="valid ExperimentPlanResult"):
        select_replay(json.loads(saved), "judge")

    with_experiment = json.loads(saved)
    with_experiment["stages"]["experiment"] = json.loads(context.experiment.model_dump_json())
    judged = select_replay(with_experiment, "judge")
    assert judged.experiment is not None
    assert judged.experiment.status == "partial"
    broken = json.loads(saved)
    broken["stages"]["experiment"] = {"status": "partial"}
    with pytest.raises(ReplayRefused, match="experiment checkpoint failed"):
        select_replay(broken, "judge")


def test_replay_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during replay import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    path = Path(__file__).resolve().parents[2] / "scripts" / "live_m4_replay.py"
    spec = importlib.util.spec_from_file_location("live_m4_replay_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.__name__ != "__main__"
