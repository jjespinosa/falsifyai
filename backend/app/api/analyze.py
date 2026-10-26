"""Parse and critique routes. There is no pipeline orchestration here."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.providers.meta import (
    ConfigurationError,
    LiveModelCallsDisabled,
    ProviderResponseError,
)
from app.schemas.critic import CritiqueInput, CritiqueReport
from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import ParserResult
from app.services.critic import critique_hypothesis
from app.services.modes import ExecutionMode
from app.services.parser import parse_hypothesis

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
) -> CritiqueReport:
    """Review claims already produced by the parser."""

    return _call(
        lambda: critique_hypothesis(
            body.hypothesis,
            body.parser_result,
            mode=mode,
            settings=request.app.state.settings,
            transport=request.app.state.live_transport,
        )
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
