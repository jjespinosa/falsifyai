"""Analysis routes. There is no pipeline orchestration here."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.providers.meta import (
    REASONING_EFFORTS,
    ConfigurationError,
    LiveModelCallsDisabled,
    ProviderResponseError,
)
from app.schemas.critic import CritiqueInput, CritiqueReport
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelInput, NullModelResult
from app.schemas.observable import ObservableDesignResult, ObservableInput
from app.schemas.parser import ParserResult
from app.schemas.experiment import ExperimentInput, ExperimentPlanResult
from app.schemas.simulation import SimulationPlanInput, SimulationPlanResult
from app.schemas.verdict import FalsificationVerdict, JudgeInput
from app.services.critic import critique_hypothesis
from app.services.experiment import design_experiment
from app.services.judge import judge_hypothesis
from app.services.modes import ExecutionMode
from app.services.null_model import build_null_model
from app.services.observable import design_observables
from app.services.parser import parse_hypothesis
from app.services.simulation_plan import plan_simulation

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])

ModeQuery = Annotated[
    ExecutionMode,
    Query(
        description=(
            "stub is the default and does not use the network. "
            "live calls the Meta Model API and does not fall back to stub."
        )
    ),
]


@router.post("/parse", response_model=ParserResult, summary="Parse a hypothesis")
def parse_route(
    hypothesis: HypothesisInput,
    request: Request,
    mode: ModeQuery = ExecutionMode.STUB,
) -> ParserResult:
    """Extract the smallest set of claims from a hypothesis."""

    return _call(
        lambda: parse_hypothesis(
            hypothesis,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
        )
    )


@router.post("/critique", response_model=CritiqueReport, summary="Critique parsed claims")
def critique_route(
    body: CritiqueInput,
    request: Request,
    mode: ModeQuery = ExecutionMode.STUB,
    reasoning_effort: Annotated[
        str,
        Query(description="Live critic reasoning effort. The M1 canary uses low."),
    ] = "low",
) -> CritiqueReport:
    """Review claims already produced by the parser."""

    if reasoning_effort not in REASONING_EFFORTS:
        raise HTTPException(
            status_code=422,
            detail="reasoning_effort must be minimal, low, medium, high, xhigh, or max.",
        )
    return _call(
        lambda: critique_hypothesis(
            body.hypothesis,
            body.parser_result,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
            reasoning_effort=reasoning_effort,
        )
    )


@router.post("/null-model", response_model=NullModelResult, summary="Build a null model")
def null_model_route(
    body: NullModelInput,
    request: Request,
    mode: ModeQuery = ExecutionMode.STUB,
    reasoning_effort: Annotated[
        str,
        Query(description="Live null-model reasoning effort. The M2 canary uses medium."),
    ] = "medium",
) -> NullModelResult:
    """Construct the strongest reasonable competing explanation."""

    _check_effort(reasoning_effort)
    return _call(
        lambda: build_null_model(
            body.hypothesis,
            body.parser_result,
            body.critique_report,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
            reasoning_effort=reasoning_effort,
        )
    )


@router.post(
    "/observable",
    response_model=ObservableDesignResult,
    summary="Design discriminating observables",
)
def observable_route(
    body: ObservableInput,
    request: Request,
    mode: ModeQuery = ExecutionMode.STUB,
    reasoning_effort: Annotated[
        str,
        Query(description="Live observable reasoning effort. The M2 canary uses medium."),
    ] = "medium",
) -> ObservableDesignResult:
    """Propose a quantity that might separate H1 from H0."""

    _check_effort(reasoning_effort)
    return _call(
        lambda: design_observables(
            body.hypothesis,
            body.parser_result,
            body.critique_report,
            body.null_model_result,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
            reasoning_effort=reasoning_effort,
        )
    )


@router.post(
    "/simulation-plan",
    response_model=SimulationPlanResult,
    summary="Plan a restricted numerical comparison",
)
def simulation_plan_route(
    body: SimulationPlanInput,
    request: Request,
    mode: ModeQuery = ExecutionMode.STUB,
    reasoning_effort: Annotated[
        str,
        Query(description="Live planner reasoning effort. The M3 canary uses medium."),
    ] = "medium",
) -> SimulationPlanResult:
    """Decide whether H0 and H1 are quantitative enough to simulate."""

    _check_effort(reasoning_effort)
    return _call(
        lambda: plan_simulation(
            body.hypothesis,
            body.parser_result,
            body.critique_report,
            body.null_model_result,
            body.observable_design,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
            reasoning_effort=reasoning_effort,
        )
    )


@router.post(
    "/experiment",
    response_model=ExperimentPlanResult,
    summary="Design a controlled comparison",
)
def experiment_route(
    body: ExperimentInput,
    request: Request,
    mode: ModeQuery = ExecutionMode.STUB,
    reasoning_effort: Annotated[
        str,
        Query(description="Live experiment reasoning effort. The M4 canary uses medium."),
    ] = "medium",
) -> ExperimentPlanResult:
    """Design a comparison. Partial is a meaningful and incomplete design."""

    _check_effort(reasoning_effort)
    return _call(
        lambda: design_experiment(
            body.hypothesis,
            body.parser_result,
            body.critique_report,
            body.null_model_result,
            body.observable_design,
            body.simulation_plan,
            body.simulation_result,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
            reasoning_effort=reasoning_effort,
        )
    )


@router.post("/judge", response_model=FalsificationVerdict, summary="Judge falsifiability")
def judge_route(
    body: JudgeInput,
    request: Request,
    mode: ModeQuery = ExecutionMode.STUB,
    reasoning_effort: Annotated[
        str,
        Query(description="Live judge reasoning effort. The M4 canary uses medium."),
    ] = "medium",
) -> FalsificationVerdict:
    """Assign one falsification status for the supplied scientific state."""

    _check_effort(reasoning_effort)
    return _call(
        lambda: judge_hypothesis(
            body.hypothesis,
            body.parser_result,
            body.critique_report,
            body.null_model_result,
            body.observable_design,
            body.simulation_plan,
            body.simulation_result,
            body.experiment_plan,
            body.capability,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
            reasoning_effort=reasoning_effort,
        )
    )


def _check_effort(reasoning_effort: str) -> None:
    if reasoning_effort not in REASONING_EFFORTS:
        raise HTTPException(
            status_code=422,
            detail="reasoning_effort must be minimal, low, medium, high, xhigh, or max.",
        )


def _call(action):
    try:
        return action()
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except LiveModelCallsDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ProviderResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
