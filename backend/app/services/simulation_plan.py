"""Simulation planner. Stub mode is deterministic. Live mode does not fall back."""

from __future__ import annotations

from app.config import Settings
from app.prompts.simulation import SIMULATION_SYSTEM_PROMPT, simulation_user_prompt
from app.providers.meta import ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.critic import CritiqueReport
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.schemas.simulation import SimulationPlanResult, SimulationSpec
from app.services.fixtures import normalize_statement
from app.services.grounding import hypothesis_source, number_is_stated
from app.services.live import complete_structured
from app.services.m3_fixtures import GOLDEN_PLANS, generic_blocked_plan
from app.services.modes import ExecutionMode


def plan_simulation(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    critique_report: CritiqueReport,
    null_model_result: NullModelResult,
    observable_design: ObservableDesignResult,
    *,
    mode: ExecutionMode,
    settings: Settings,
    transport: ModelTransport | None = None,
    reasoning_effort: str = "medium",
) -> SimulationPlanResult:
    """Decide whether H0 and H1 can be computed. A live failure stays a live failure."""

    if mode is ExecutionMode.STUB:
        result = _stub_plan(hypothesis, observable_design)
    elif mode is ExecutionMode.LIVE:
        result = complete_structured(
            settings,
            transport,
            system=SIMULATION_SYSTEM_PROMPT,
            user=simulation_user_prompt(
                hypothesis_payload=hypothesis.model_dump_json(),
                parser_payload=parser_result.model_dump_json(),
                critique_payload=critique_report.model_dump_json(),
                null_model_payload=null_model_result.model_dump_json(),
                observable_payload=observable_design.model_dump_json(),
            ),
            schema_name="SimulationPlanResult",
            model=SimulationPlanResult,
            reasoning_effort=reasoning_effort,
        )
    else:
        raise ValueError("unsupported execution mode")
    return _guard(hypothesis, observable_design, result)


def _stub_plan(
    hypothesis: HypothesisInput,
    observable_design: ObservableDesignResult,
) -> SimulationPlanResult:
    builder = GOLDEN_PLANS.get(normalize_statement(hypothesis.statement))
    if builder is not None:
        return builder()
    observable_id = (
        observable_design.observables[0].observable_id if observable_design.observables else None
    )
    return generic_blocked_plan(observable_id)


def _guard(
    hypothesis: HypothesisInput,
    observable_design: ObservableDesignResult,
    result: SimulationPlanResult,
) -> SimulationPlanResult:
    known = {item.observable_id for item in observable_design.observables}
    if result.observable_id is not None and result.observable_id not in known:
        raise ProviderResponseError("observable_id does not exist in the observable design")
    if result.status == "blocked" or result.spec is None:
        return result
    selected = next(
        item for item in observable_design.observables if item.observable_id == result.observable_id
    )
    if not selected.discriminating:
        return _blocked(
            result.observable_id,
            "The selected observable does not yet separate H1 from H0.",
        )
    missing = _unstated_coefficients(hypothesis, result.spec)
    if missing:
        return _blocked(
            result.observable_id,
            "A quantitative H1 relationship is required before a numerical "
            "H0/H1 comparison can be simulated.",
        )
    return result


def _unstated_coefficients(hypothesis: HypothesisInput, spec: SimulationSpec) -> list[float]:
    source = hypothesis_source(hypothesis)
    numbers: list[float] = []
    for curve in (spec.h0, spec.h1):
        for value in curve.parameters.model_dump().values():
            if value is not None and not number_is_stated(float(value), source):
                numbers.append(float(value))
    for value in (spec.independent_variable.min, spec.independent_variable.max):
        if not number_is_stated(value, source):
            numbers.append(value)
    if spec.sweep is not None:
        for value in (spec.sweep.min, spec.sweep.max):
            if not number_is_stated(value, source):
                numbers.append(value)
    return numbers


def _blocked(observable_id: str | None, reason: str) -> SimulationPlanResult:
    return SimulationPlanResult(
        status="blocked",
        observable_id=observable_id,
        spec=None,
        blocking_missing_definitions=[reason],
        assumptions=[],
        summary="Simulation is blocked. No quantitative law was invented.",
    )
