"""Experiment designer. Stub mode is deterministic. Live mode does not fall back."""

from __future__ import annotations

import re

from app.config import Settings
from app.prompts.experiment import EXPERIMENT_SYSTEM_PROMPT, experiment_user_prompt
from app.providers.meta import ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.critic import CritiqueReport
from app.schemas.experiment import (
    SAFETY_NOTE,
    ExperimentPlan,
    ExperimentPlanResult,
    ExperimentVariable,
    ParameterScan,
    RequiredResolution,
)
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.schemas.simulation import SimulationPlanResult, SimulationResult
from app.services.fixtures import normalize_statement
from app.services.grounding import hypothesis_source, number_is_stated
from app.services.live import complete_structured
from app.services.m4_fixtures import GOLDEN_EXPERIMENTS, safety_blocked_experiment
from app.services.modes import ExecutionMode

_HAZARD = re.compile(r"\b(sarin|weaponized anthrax|enrich uranium)\b", re.IGNORECASE)


def design_experiment(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    critique_report: CritiqueReport,
    null_model_result: NullModelResult,
    observable_design: ObservableDesignResult,
    simulation_plan: SimulationPlanResult,
    simulation_result: SimulationResult | None,
    *,
    mode: ExecutionMode,
    settings: Settings,
    transport: ModelTransport | None = None,
    reasoning_effort: str = "medium",
) -> ExperimentPlanResult:
    """Design a comparison. A blocked simulation does not by itself block the design."""

    if _HAZARD.search(hypothesis.statement):
        return safety_blocked_experiment()
    if mode is ExecutionMode.STUB:
        result = _stub(hypothesis, parser_result, observable_design)
    elif mode is ExecutionMode.LIVE:
        claim_ids = ",".join(claim.claim_id for claim in parser_result.claims) or "none"
        observable_ids = ",".join(item.observable_id for item in observable_design.observables) or "none"
        result = complete_structured(
            settings,
            transport,
            system=EXPERIMENT_SYSTEM_PROMPT,
            user=experiment_user_prompt(
                hypothesis_payload=hypothesis.model_dump_json(),
                parser_payload=parser_result.model_dump_json(),
                critique_payload=critique_report.model_dump_json(),
                null_model_payload=null_model_result.model_dump_json(),
                observable_payload=observable_design.model_dump_json(),
                simulation_plan_payload=simulation_plan.model_dump_json(),
                simulation_result_payload=(
                    "null" if simulation_result is None else simulation_result.model_dump_json()
                ),
                claim_ids=claim_ids,
                observable_ids=observable_ids,
            ),
            schema_name="ExperimentPlanResult",
            model=ExperimentPlanResult,
            reasoning_effort=reasoning_effort,
        )
    else:
        raise ValueError("unsupported execution mode")
    _guard(hypothesis, parser_result, observable_design, result)
    return result


def _stub(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    observable_design: ObservableDesignResult,
) -> ExperimentPlanResult:
    builder = GOLDEN_EXPERIMENTS.get(normalize_statement(hypothesis.statement))
    if builder is not None:
        return builder()
    if not observable_design.observables or not parser_result.claims:
        return ExperimentPlanResult(
            status="blocked",
            experiment=None,
            blocking_missing_definitions=[
                "No observable and claim pair is available for a controlled comparison."
            ],
            summary="Experiment design is blocked until a measurable comparison exists.",
        )
    observable = observable_design.observables[0]
    claim_id = parser_result.claims[0].claim_id
    plan = ExperimentPlan(
        experiment_id="exp1",
        objective=f"Measure {observable.name} under the controls already named for {claim_id}.",
        target_claim_ids=[claim_id],
        observable_ids=[observable.observable_id],
        independent_variables=[
            ExperimentVariable(name=observable.name, units=observable.units, capability="unknown")
        ],
        measured_variables=[
            ExperimentVariable(name=observable.name, units=observable.units, capability="required")
        ],
        controlled_variables=[
            ExperimentVariable(name="stated controls", units="unspecified", capability="required")
        ],
        control_groups=["the same stated procedure"],
        parameter_scan=[
            ParameterScan(
                name=observable.name,
                units=observable.units,
                lower=None,
                upper=None,
                status="undefined",
            )
        ],
        required_resolution=RequiredResolution(
            observable_id=observable.observable_id,
            value=None,
            units=observable.units,
            basis="No minimum effect or resolution was supplied.",
            status="undefined",
        ),
        confounders=list(observable.known_confounders),
        procedure_outline=["Apply the stated controls and record the selected observable."],
        stop_conditions=["Stop if a named control cannot be held."],
        falsifier_candidate=(
            "A difference larger than a not-yet-specified minimum would address H0. "
            "No minimum is stated."
        ),
        limitations=["The decisive resolution is undefined."],
        safety_notes=[SAFETY_NOTE],
    )
    return ExperimentPlanResult(
        status="partial",
        experiment=plan,
        blocking_missing_definitions=["A minimum effect or required resolution is not defined."],
        summary="A comparison can be described, and its decisive resolution is undefined.",
    )


def _guard(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    observable_design: ObservableDesignResult,
    result: ExperimentPlanResult,
) -> None:
    plan = result.experiment
    if plan is None:
        return
    claims = {claim.claim_id for claim in parser_result.claims}
    observables = {item.observable_id for item in observable_design.observables}
    unknown_claims = [item for item in plan.target_claim_ids if item not in claims]
    if unknown_claims:
        raise ProviderResponseError("target_claim_ids do not exist in the parser result")
    unknown_observables = [item for item in plan.observable_ids if item not in observables]
    if unknown_observables:
        raise ProviderResponseError("observable_ids do not exist in the observable design")
    source = hypothesis_source(hypothesis)
    resolution = plan.required_resolution
    if resolution.status == "defined" and not number_is_stated(float(resolution.value), source):
        raise ProviderResponseError("required resolution was not supplied in the hypothesis")
    for scan in plan.parameter_scan:
        if scan.status != "defined":
            continue
        if not number_is_stated(float(scan.lower), source) or not number_is_stated(
            float(scan.upper), source
        ):
            raise ProviderResponseError("a scan bound was not supplied in the hypothesis")
