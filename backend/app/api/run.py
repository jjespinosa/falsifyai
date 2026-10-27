"""One synchronous run and the demo catalog. There is no background worker."""

from fastapi import APIRouter, Request

from app.schemas.run import ExampleList, RunRequest, RunResult
from app.services.demo_fixtures import demo_examples
from app.services.run import execute_run

router = APIRouter(prefix="/api/v1", tags=["run"])


@router.post("/run", response_model=RunResult, summary="Try to falsify one hypothesis")
def run_route(body: RunRequest, request: Request) -> RunResult:
    """Execute the verified pipeline once.

    Stub is the default. A scientific blocker is a completed response, not an HTTP error.
    """

    return execute_run(
        body,
        settings=request.app.state.settings,
        transport=request.app.state.live_transport,
    )


@router.get("/examples", response_model=ExampleList, summary="Demo hypotheses")
def examples_route() -> ExampleList:
    """Return the three fixed demos."""

    return demo_examples()
