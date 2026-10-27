"""Planner fixtures. The synthetic curve is an engine check, not a claim."""

from app.schemas.simulation import (
    FamilyParameters,
    IndependentVariable,
    ModelCurve,
    SimulationPlanResult,
    SimulationSpec,
)
from app.services.fixtures import normalize_statement
from app.services.m2_fixtures import CASE_MASS

SYNTHETIC_CURVE = (
    "Synthetic engine check only, not a scientific claim. "
    "Compare y = 2*x + 1 with y = 2*x + 1 + 0.1*x*x for x from 0 to 10 inclusive."
)

QUANTITATIVE_H1_BLOCKER = (
    "A quantitative H1 relationship between bob mass and oscillation period "
    "is required before a numerical H0/H1 comparison can be simulated."
)


def family_parameters(**known: float) -> FamilyParameters:
    """Fill the closed parameter object, leaving unused coefficients null."""

    data: dict[str, float | None] = {
        "value": None,
        "slope": None,
        "intercept": None,
        "quadratic": None,
        "amplitude": None,
        "rate": None,
        "offset": None,
    }
    data.update(known)
    return FamilyParameters.model_validate(data)


def synthetic_spec() -> SimulationSpec:
    """H0 is 2x+1 and H1 adds 0.1*x^2 on x from 0 to 10."""

    return SimulationSpec(
        simulation_id="sim1",
        observable_id="o1",
        template="static_curve",
        independent_variable=IndependentVariable(
            name="x",
            units="1",
            min=0,
            max=10,
            points=11,
        ),
        h0=ModelCurve(
            family="linear",
            parameters=family_parameters(slope=2, intercept=1),
        ),
        h1=ModelCurve(
            family="quadratic",
            parameters=family_parameters(quadratic=0.1, slope=2, intercept=1),
        ),
        outputs=["h0", "h1", "delta"],
        assumptions=["Synthetic engine fixture. This is not a scientific claim."],
        seed=12345,
        sweep=None,
    )


def case_mass_plan() -> SimulationPlanResult:
    """The mass hypothesis has no quantitative H1, so the plan stays blocked."""

    return SimulationPlanResult(
        status="blocked",
        observable_id="o1",
        spec=None,
        blocking_missing_definitions=[QUANTITATIVE_H1_BLOCKER],
        assumptions=[
            "The conventional ideal pendulum period does not supply an H1 mass dependence."
        ],
        summary=(
            "Simulation is blocked. H1 does not define a quantitative mass-to-period "
            "relationship, so no curve was invented."
        ),
    )


def synthetic_plan() -> SimulationPlanResult:
    """A ready plan whose coefficients are written in the synthetic statement."""

    spec = synthetic_spec()
    return SimulationPlanResult(
        status="ready",
        observable_id=spec.observable_id,
        spec=spec,
        blocking_missing_definitions=[],
        assumptions=list(spec.assumptions),
        summary=(
            "The synthetic statement already defines both curves, so the registered "
            "linear and quadratic families can be compared. This comparison does not decide the hypothesis."
        ),
    )


def generic_blocked_plan(observable_id: str | None) -> SimulationPlanResult:
    return SimulationPlanResult(
        status="blocked",
        observable_id=observable_id,
        spec=None,
        blocking_missing_definitions=[
            "A quantitative relationship for H1 is required before H0 and H1 can be simulated."
        ],
        assumptions=[],
        summary="Simulation is blocked. No quantitative comparison was invented.",
    )


GOLDEN_PLANS = {
    normalize_statement(CASE_MASS): case_mass_plan,
    normalize_statement(SYNTHETIC_CURVE): synthetic_plan,
}
