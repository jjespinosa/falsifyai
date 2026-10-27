"""Local numerical route. It does not call the Meta Model API."""

from fastapi import APIRouter, HTTPException

from app.schemas.simulation import SimulationResult, SimulationSpec
from app.simulation.engine import SimulationRejected, run_simulation

router = APIRouter(prefix="/api/v1", tags=["simulate"])


@router.post("/simulate", response_model=SimulationResult, summary="Run a declarative simulation")
def simulate_route(spec: SimulationSpec) -> SimulationResult:
    """Evaluate a validated spec with a registered numerical family."""

    try:
        return run_simulation(spec)
    except SimulationRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
