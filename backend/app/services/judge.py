"""Falsification judge. Stub mode is deterministic. Live mode does not fall back."""

from __future__ import annotations

from app.config import Settings
from app.prompts.judge import JUDGE_SYSTEM_PROMPT, judge_user_prompt
from app.providers.meta import ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.critic import CritiqueReport
from app.schemas.experiment import ExperimentPlanResult
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult, PredictedDifference
from app.schemas.parser import ParserResult
from app.schemas.simulation import SimulationPlanResult, SimulationResult
from app.schemas.verdict import ExperimentalCapability, FalsificationVerdict
from app.services.fixtures import normalize_statement
from app.services.live import complete_structured
from app.services.m4_fixtures import GOLDEN_VERDICTS
from app.services.modes import ExecutionMode


def judge_hypothesis(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    critique_report: CritiqueReport,
    null_model_result: NullModelResult,
    observable_design: ObservableDesignResult,
    simulation_plan: SimulationPlanResult,
    simulation_result: SimulationResult | None,
    experiment_plan: ExperimentPlanResult,
    capability: ExperimentalCapability | None,
    *,
    mode: ExecutionMode,
    settings: Settings,
    transport: ModelTransport | None = None,
    reasoning_effort: str = "medium",
) -> FalsificationVerdict:
    """Assign one falsification status. A live failure stays a live failure."""

    if mode is ExecutionMode.STUB:
        result = _stub(hypothesis, parser_result, experiment_plan, simulation_plan)
    elif mode is ExecutionMode.LIVE:
        allowed = known_evidence_refs(
            parser_result,
            null_model_result,
            observable_design,
            experiment_plan,
            simulation_plan,
            simulation_result,
        )
        result = complete_structured(
            settings,
            transport,
            system=JUDGE_SYSTEM_PROMPT,
            user=judge_user_prompt(
                hypothesis_payload=hypothesis.model_dump_json(),
                parser_payload=parser_result.model_dump_json(),
                critique_payload=critique_report.model_dump_json(),
                null_model_payload=null_model_result.model_dump_json(),
                observable_payload=observable_design.model_dump_json(),
                simulation_plan_payload=simulation_plan.model_dump_json(),
                simulation_result_payload=(
                    "null" if simulation_result is None else simulation_result.model_dump_json()
                ),
                experiment_payload=experiment_plan.model_dump_json(),
                capability_payload="null" if capability is None else capability.model_dump_json(),
                allowed_refs=",".join(sorted(allowed)) or "none",
            ),
            schema_name="FalsificationVerdict",
            model=FalsificationVerdict,
            reasoning_effort=reasoning_effort,
        )
    else:
        raise ValueError("unsupported execution mode")
    check_verdict(
        result,
        observable_design,
        simulation_plan,
        experiment_plan,
        capability,
        parser_result,
        null_model_result,
        simulation_result,
    )
    return result


def known_evidence_refs(
    parser_result: ParserResult,
    null_model_result: NullModelResult,
    observable_design: ObservableDesignResult,
    experiment_plan: ExperimentPlanResult,
    simulation_plan: SimulationPlanResult,
    simulation_result: SimulationResult | None,
) -> set[str]:
    """Ids the verdict is allowed to cite."""

    refs = {claim.claim_id for claim in parser_result.claims}
    refs.update(model.model_id for model in null_model_result.models)
    refs.update(item.observable_id for item in observable_design.observables)
    if experiment_plan.experiment is not None:
        refs.add(experiment_plan.experiment.experiment_id)
    if simulation_plan.spec is not None:
        refs.add(simulation_plan.spec.simulation_id)
    if simulation_result is not None:
        refs.add(simulation_result.simulation_id)
    return refs


def check_verdict(
    verdict: FalsificationVerdict,
    observable_design: ObservableDesignResult,
    simulation_plan: SimulationPlanResult,
    experiment_plan: ExperimentPlanResult,
    capability: ExperimentalCapability | None,
    parser_result: ParserResult,
    null_model_result: NullModelResult,
    simulation_result: SimulationResult | None,
) -> None:
    """Reject a status the supplied state does not support."""

    allowed = known_evidence_refs(
        parser_result,
        null_model_result,
        observable_design,
        experiment_plan,
        simulation_plan,
        simulation_result,
    )
    unknown = [item for item in verdict.evidence_refs if item not in allowed]
    if unknown:
        raise ProviderResponseError("evidence_refs refer to an unknown id")
    if verdict.status == "TESTABLE":
        _require_testable_state(observable_design, simulation_plan, experiment_plan, capability)
    elif verdict.status == "BELOW_SENSITIVITY":
        _require_below_sensitivity(
            observable_design, simulation_plan, experiment_plan, capability
        )
    elif verdict.status == "NON_DISCRIMINATING":
        _require_non_discriminating(observable_design, experiment_plan)
    elif verdict.status == "NOT_YET_FALSIFIABLE" and verdict.delta_over_sigma is not None:
        if simulation_plan.status != "ready" or capability is None:
            raise ProviderResponseError("delta_over_sigma needs a supplied difference and uncertainty")


def _require_testable_state(
    observable_design: ObservableDesignResult,
    simulation_plan: SimulationPlanResult,
    experiment_plan: ExperimentPlanResult,
    capability: ExperimentalCapability | None,
) -> None:
    plan = experiment_plan.experiment
    if (
        experiment_plan.status != "ready"
        or plan is None
        or plan.required_resolution.status != "defined"
    ):
        raise ProviderResponseError("TESTABLE requires a defined resolution")
    if simulation_plan.status != "ready":
        raise ProviderResponseError("TESTABLE requires quantitative discrimination")
    selected = [
        item for item in observable_design.observables if item.observable_id in plan.observable_ids
    ]
    if not selected or any(not item.discriminating for item in selected):
        raise ProviderResponseError("TESTABLE requires a discriminating observable")
    if any(item.predicted_difference is PredictedDifference.ZERO for item in selected):
        raise ProviderResponseError("TESTABLE requires quantitative discrimination")
    if capability is None or plan.required_resolution.value is None:
        return
    if capability.observable_id != plan.required_resolution.observable_id:
        raise ProviderResponseError("capability observable_id does not match the experiment")
    if capability.units != plan.required_resolution.units:
        raise ProviderResponseError("capability units do not match the required resolution")
    if capability.uncertainty > plan.required_resolution.value:
        raise ProviderResponseError("TESTABLE requires the supplied capability to meet the resolution")


def _require_below_sensitivity(
    observable_design: ObservableDesignResult,
    simulation_plan: SimulationPlanResult,
    experiment_plan: ExperimentPlanResult,
    capability: ExperimentalCapability | None,
) -> None:
    plan = experiment_plan.experiment
    if capability is None:
        raise ProviderResponseError("BELOW_SENSITIVITY requires explicit capability")
    _require_testable_state(observable_design, simulation_plan, experiment_plan, None)
    if plan is None or plan.required_resolution.value is None:
        raise ProviderResponseError("BELOW_SENSITIVITY requires a defined resolution")
    if capability.observable_id != plan.required_resolution.observable_id:
        raise ProviderResponseError("capability observable_id does not match the experiment")
    if capability.units != plan.required_resolution.units:
        raise ProviderResponseError("capability units do not match the required resolution")
    if capability.uncertainty <= plan.required_resolution.value:
        raise ProviderResponseError("BELOW_SENSITIVITY requires an insufficient explicit capability")


def _require_non_discriminating(
    observable_design: ObservableDesignResult,
    experiment_plan: ExperimentPlanResult,
) -> None:
    plan = experiment_plan.experiment
    if plan is None:
        return
    selected = [
        item for item in observable_design.observables if item.observable_id in plan.observable_ids
    ]
    if any(
        item.discriminating and item.predicted_difference is not PredictedDifference.ZERO
        for item in selected
    ):
        raise ProviderResponseError("NON_DISCRIMINATING requires H0 and H1 to agree")


def _stub(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    experiment_plan: ExperimentPlanResult,
    simulation_plan: SimulationPlanResult,
) -> FalsificationVerdict:
    builder = GOLDEN_VERDICTS.get(normalize_statement(hypothesis.statement))
    if builder is not None:
        return builder()
    refs = [claim.claim_id for claim in parser_result.claims][:1] or ["c1"]
    if experiment_plan.experiment is not None:
        refs.append(experiment_plan.experiment.experiment_id)
    if simulation_plan.spec is not None:
        refs.append(simulation_plan.spec.simulation_id)
    return FalsificationVerdict(
        status="NOT_YET_FALSIFIABLE",
        primary_reason="The supplied state does not yet define a finite falsifier.",
        falsifier="No operational falsifier is defined yet.",
        required_next_definition="Specify the quantitative comparison a finite measurement could miss.",
        delta_over_sigma=None,
        limitations=["No supplied uncertainty was used."],
        evidence_refs=list(dict.fromkeys(refs)),
    )
