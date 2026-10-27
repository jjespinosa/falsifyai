"""Experiment and verdict fixtures. Synthetic cases are not laboratory evidence."""

from app.schemas.claim import ClaimProvenance, EpistemicStatus, EvidenceOrigin
from app.schemas.critic import assemble_report
from app.schemas.experiment import (
    SAFETY_NOTE,
    ExperimentPlan,
    ExperimentPlanResult,
    ExperimentVariable,
    ParameterScan,
    RequiredResolution,
)
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import KnowledgeBasis, NullModel, NullModelResult, SourcedStatement
from app.schemas.observable import ObservableCandidate, ObservableDesignResult, PredictedDifference
from app.schemas.parser import (
    ClaimType,
    ClaimVariable,
    ExtractionConfidence,
    ParsedClaim,
    ParserResult,
)
from app.schemas.simulation import SimulationPlanResult
from app.schemas.verdict import ExperimentalCapability, FalsificationVerdict
from app.services.fixtures import CASE_B, normalize_statement
from app.services.m2_fixtures import CASE_MASS, case_mass_null, case_mass_observable
from app.services.m3_fixtures import case_mass_plan, family_parameters, synthetic_plan
from app.schemas.simulation import IndependentVariable, ModelCurve, SimulationSpec

NEXT_QUANTITATIVE_DEFINITION = (
    "Specify a quantitative mass-to-period relationship, bounded parameter range, "
    "or minimum effect size that H1 requires."
)

CASE_QUANT = (
    "Synthetic quantitative check, not a scientific claim. "
    "H0 is y = 2*x + 1 and H1 is y = 2*x + 1 + 0.1*x*x for x from 0 to 10 inclusive. "
    "Fixture-supplied measurement uncertainty is 0.1 units."
)

CASE_LOW = (
    "Synthetic sensitivity check, not a scientific claim. "
    "H0 is y = 2*x + 1 and H1 is y = 2*x + 1.001. "
    "The constant difference is 0.001 for x from 0 to 10 inclusive. "
    "Fixture-supplied measurement uncertainty is 1 unit."
)

CASE_SAME = (
    "Synthetic identical-prediction check, not a scientific claim. "
    "H0 and H1 both give y = 2*x + 1 for x from 0 to 10 inclusive."
)


def _variable(name: str, units: str, capability: str) -> ExperimentVariable:
    return ExperimentVariable(name=name, units=units, capability=capability)  # type: ignore[arg-type]


def _claim(statement: str) -> ParserResult:
    return ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement=statement,
                claim_type=ClaimType.CAUSAL,
                variables=[
                    ClaimVariable(name="x", defined=True),
                    ClaimVariable(name="y", defined=True),
                ],
                is_operational=True,
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.HYPOTHESIS,
                confidence=ExtractionConfidence.MEDIUM,
            )
        ]
    )


def _null(description: str) -> NullModelResult:
    return NullModelResult(
        models=[
            NullModel(
                model_id="h0",
                description=description,
                target_claim_ids=["c1"],
                equations=[
                    SourcedStatement(
                        statement=description,
                        basis=KnowledgeBasis.USER_SUPPLIED,
                    )
                ],
                can_mimic_claim=False,
                mimicry_reason="The fixture states H0 directly.",
                basis=KnowledgeBasis.USER_SUPPLIED,
            )
        ],
        summary="Fixture H0 for a synthetic comparison.",
    )


def _observable(
    *,
    h0: str,
    h1: str,
    difference: PredictedDifference,
    discriminating: bool,
) -> ObservableDesignResult:
    return ObservableDesignResult(
        observables=[
            ObservableCandidate(
                observable_id="o1",
                name="response y",
                symbol="y",
                definition="The response y at a stated x in this synthetic fixture.",
                units="1",
                measurement_method="Read y at the stated x. No laboratory instrument is implied.",
                target_claim_ids=["c1"],
                h1_prediction=h1,
                h0_prediction=h0,
                predicted_difference=difference,
                required_controls=["the same stated x grid"],
                known_confounders=[],
                blocking_missing_definitions=[],
                discriminating=discriminating,
            )
        ],
        summary="Synthetic observable for an engine or verdict fixture.",
    )


def _ready_curve(h1_intercept: float, h1_quadratic: float | None) -> SimulationPlanResult:
    h1_family = "quadratic" if h1_quadratic is not None else "linear"
    h1_parameters = family_parameters(slope=2, intercept=h1_intercept)
    if h1_quadratic is not None:
        h1_parameters = family_parameters(quadratic=h1_quadratic, slope=2, intercept=h1_intercept)
    spec = SimulationSpec(
        simulation_id="sim1",
        observable_id="o1",
        template="static_curve",
        independent_variable=IndependentVariable(name="x", units="1", min=0, max=10, points=11),
        h0=ModelCurve(family="linear", parameters=family_parameters(slope=2, intercept=1)),
        h1=ModelCurve(family=h1_family, parameters=h1_parameters),  # type: ignore[arg-type]
        outputs=["h0", "h1", "delta"],
        assumptions=["Synthetic fixture curve."],
        seed=12345,
        sweep=None,
    )
    return SimulationPlanResult(
        status="ready",
        observable_id="o1",
        spec=spec,
        blocking_missing_definitions=[],
        assumptions=["Synthetic fixture curve."],
        summary="Both curves are written numerically in the fixture.",
    )


def pendulum_experiment() -> ExperimentPlanResult:
    plan = ExperimentPlan(
        experiment_id="exp1",
        objective=(
            "Compare oscillation period across bob masses while length, angle, "
            "geometry, and protocol stay fixed."
        ),
        target_claim_ids=["c1"],
        observable_ids=["o1"],
        independent_variables=[_variable("bob mass", "unspecified", "unknown")],
        measured_variables=[_variable("oscillation period", "s", "required")],
        controlled_variables=[
            _variable("effective length", "unspecified", "required"),
            _variable("release angle", "unspecified", "required"),
            _variable("bob geometry and center of mass", "unspecified", "required"),
            _variable("string and pivot", "unspecified", "required"),
            _variable("air and protocol", "unspecified", "required"),
            _variable("location and gravity", "unspecified", "required"),
        ],
        control_groups=["the same support, release, and timing procedure"],
        parameter_scan=[
            ParameterScan(
                name="bob mass",
                units="unspecified",
                lower=None,
                upper=None,
                status="undefined",
            )
        ],
        required_resolution=RequiredResolution(
            observable_id="o1",
            value=None,
            units="s",
            basis="H1 states no minimum period change, so no resolution can be computed.",
            status="undefined",
        ),
        confounders=[
            "bob size",
            "aerodynamic drag",
            "initial amplitude",
            "distance from the pivot to the center of mass",
        ],
        procedure_outline=[
            "Hold effective length and the small release angle fixed.",
            "Change bob mass while geometry, string, pivot, air, and location stay controlled.",
            "Record the oscillation period with the same timing procedure.",
        ],
        stop_conditions=["Stop if length or release angle cannot be held fixed."],
        falsifier_candidate=(
            "A period change larger than a not-yet-specified minimum, at fixed length "
            "and angle, would count against the mass-independent account."
        ),
        limitations=[
            "H1 gives no magnitude, so an arbitrarily small mass dependence remains open."
        ],
        safety_notes=[SAFETY_NOTE],
    )
    return ExperimentPlanResult(
        status="partial",
        experiment=plan,
        blocking_missing_definitions=[NEXT_QUANTITATIVE_DEFINITION],
        summary=(
            "A mass sweep at fixed length and angle is meaningful, and the required "
            "period resolution is still undefined."
        ),
    )


def pendulum_verdict() -> FalsificationVerdict:
    return FalsificationVerdict(
        status="NOT_YET_FALSIFIABLE",
        primary_reason=(
            "H1 permits an arbitrarily small nonzero dependence of period on mass, "
            "so no finite resolution can exclude every such effect."
        ),
        falsifier=(
            "A stated minimum period change at fixed length and angle could be "
            "missed or found by a period measurement. No minimum is stated."
        ),
        required_next_definition=NEXT_QUANTITATIVE_DEFINITION,
        delta_over_sigma=None,
        limitations=["No instrument resolution was supplied."],
        evidence_refs=["c1", "h0", "o1", "exp1"],
    )


def quantitative_experiment() -> ExperimentPlanResult:
    plan = ExperimentPlan(
        experiment_id="exp1",
        objective="Compare the stated linear and quadratic responses over the stated x range.",
        target_claim_ids=["c1"],
        observable_ids=["o1"],
        independent_variables=[_variable("x", "1", "user_supplied")],
        measured_variables=[_variable("y", "1", "required")],
        controlled_variables=[_variable("the stated x grid", "1", "user_supplied")],
        control_groups=["the same stated x values"],
        parameter_scan=[
            ParameterScan(name="x", units="1", lower=0, upper=10, status="defined")
        ],
        required_resolution=RequiredResolution(
            observable_id="o1",
            value=0.1,
            units="1",
            basis="The fixture states a measurement uncertainty of 0.1 units.",
            status="defined",
        ),
        confounders=[],
        procedure_outline=[
            "Evaluate y at the stated x values from 0 to 10.",
            "Compare the readings with 2*x + 1 and with the added 0.1*x*x term.",
        ],
        stop_conditions=["Stop if the stated x range cannot be covered."],
        falsifier_candidate=(
            "Readings that stay inside the stated 0.1 uncertainty of 2*x + 1 "
            "would miss the stated quadratic term."
        ),
        limitations=["Synthetic fixture. This is not a laboratory result."],
        safety_notes=[SAFETY_NOTE],
    )
    return ExperimentPlanResult(
        status="ready",
        experiment=plan,
        blocking_missing_definitions=[],
        summary="The fixture states both curves, the x range, and a 0.1 uncertainty.",
    )


def quantitative_capability() -> ExperimentalCapability:
    return ExperimentalCapability(
        observable_id="o1",
        uncertainty=0.1,
        units="1",
        source="fixture_supplied",
    )


def quantitative_verdict() -> FalsificationVerdict:
    return FalsificationVerdict(
        status="TESTABLE",
        primary_reason=(
            "The stated quadratic difference grows to 10 at x = 10, which is larger "
            "than the fixture-supplied uncertainty of 0.1."
        ),
        falsifier=(
            "Measurements that remain inside 0.1 of 2*x + 1 across the stated range "
            "would miss the stated 0.1*x*x term."
        ),
        required_next_definition=None,
        delta_over_sigma=100.0,
        limitations=["Synthetic fixture. This is not a laboratory result."],
        evidence_refs=["c1", "h0", "o1", "exp1", "sim1"],
    )


def low_sensitivity_experiment() -> ExperimentPlanResult:
    plan = ExperimentPlan(
        experiment_id="exp1",
        objective="Compare the stated curves whose constant difference is 0.001.",
        target_claim_ids=["c1"],
        observable_ids=["o1"],
        independent_variables=[_variable("x", "1", "user_supplied")],
        measured_variables=[_variable("y", "1", "required")],
        controlled_variables=[_variable("the stated x grid", "1", "user_supplied")],
        control_groups=["the same stated x values"],
        parameter_scan=[
            ParameterScan(name="x", units="1", lower=0, upper=10, status="defined")
        ],
        required_resolution=RequiredResolution(
            observable_id="o1",
            value=0.001,
            units="1",
            basis="The fixture states a constant difference of 0.001.",
            status="defined",
        ),
        confounders=[],
        procedure_outline=[
            "Read y across the stated x range.",
            "Ask whether the readings resolve a difference of 0.001.",
        ],
        stop_conditions=["Stop if the stated uncertainty stays coarser than 0.001."],
        falsifier_candidate=(
            "A measurement uncertainty at or below 0.001 could miss or find the stated difference."
        ),
        limitations=["The fixture-supplied uncertainty is coarser than 0.001."],
        safety_notes=[SAFETY_NOTE],
    )
    return ExperimentPlanResult(
        status="ready",
        experiment=plan,
        blocking_missing_definitions=[],
        summary="The difference and the coarser fixture uncertainty are both stated.",
    )


def low_sensitivity_capability() -> ExperimentalCapability:
    return ExperimentalCapability(
        observable_id="o1",
        uncertainty=1,
        units="1",
        source="fixture_supplied",
    )


def low_sensitivity_verdict() -> FalsificationVerdict:
    return FalsificationVerdict(
        status="BELOW_SENSITIVITY",
        primary_reason=(
            "The stated difference is 0.001 and the fixture-supplied uncertainty is 1."
        ),
        falsifier=(
            "An uncertainty at or below 0.001 would be able to miss the stated difference."
        ),
        required_next_definition="A measurement uncertainty at or below 0.001 units.",
        delta_over_sigma=0.001,
        limitations=["The supplied uncertainty is coarser than the stated difference."],
        evidence_refs=["c1", "h0", "o1", "exp1", "sim1"],
    )


def identical_experiment() -> ExperimentPlanResult:
    plan = ExperimentPlan(
        experiment_id="exp1",
        objective="Measure y where H0 and H1 already state the same curve.",
        target_claim_ids=["c1"],
        observable_ids=["o1"],
        independent_variables=[_variable("x", "1", "user_supplied")],
        measured_variables=[_variable("y", "1", "required")],
        controlled_variables=[_variable("the stated x grid", "1", "user_supplied")],
        control_groups=["the same stated x values"],
        parameter_scan=[
            ParameterScan(
                name="x",
                units="1",
                lower=None,
                upper=None,
                status="undefined",
            )
        ],
        required_resolution=RequiredResolution(
            observable_id="o1",
            value=None,
            units="1",
            basis="H0 and H1 state the same y, so no separating resolution exists.",
            status="undefined",
        ),
        confounders=[],
        procedure_outline=["Read y at the stated x values and compare it with 2*x + 1."],
        stop_conditions=["Stop once both models are confirmed to state the same y."],
        falsifier_candidate="No reading of y can separate two models that state the same curve.",
        limitations=["The stated predictions are identical over the stated range."],
        safety_notes=[SAFETY_NOTE],
    )
    return ExperimentPlanResult(
        status="partial",
        experiment=plan,
        blocking_missing_definitions=["H0 and H1 predict the same y over the stated range."],
        summary="The comparison is defined, and the two predictions do not separate.",
    )


def identical_verdict() -> FalsificationVerdict:
    return FalsificationVerdict(
        status="NON_DISCRIMINATING",
        primary_reason="H0 and H1 both state y = 2*x + 1 over the stated range.",
        falsifier="No measured difference in y can separate those two statements.",
        required_next_definition=None,
        delta_over_sigma=None,
        limitations=["The observable is shared by both curves."],
        evidence_refs=["c1", "h0", "o1", "exp1"],
    )


def blocked_experiment() -> ExperimentPlanResult:
    return ExperimentPlanResult(
        status="blocked",
        experiment=None,
        blocking_missing_definitions=[
            "The claimed effect has no measurable comparison."
        ],
        summary="No controlled comparison can be designed until the effect is a quantity.",
    )


def safety_blocked_experiment() -> ExperimentPlanResult:
    return ExperimentPlanResult(
        status="blocked",
        experiment=None,
        blocking_missing_definitions=[
            "Hazardous procedure details are not generated. No autonomous physical execution."
        ],
        summary="The request stays at a non-actionable safety stop.",
    )


class M4Context:
    """One stubbed scientific state for a verdict fixture."""

    def __init__(
        self,
        statement: str,
        *,
        parser_result: ParserResult,
        null_model: NullModelResult,
        observables: ObservableDesignResult,
        simulation_plan: SimulationPlanResult,
        experiment: ExperimentPlanResult,
        verdict: FalsificationVerdict | None = None,
        capability: ExperimentalCapability | None = None,
    ) -> None:
        self.hypothesis = HypothesisInput(statement=statement)
        self.parser_result = parser_result
        self.critique = assemble_report(issues=[], summary="Fixture context for a verdict check.")
        self.null_model = null_model
        self.observables = observables
        self.simulation_plan = simulation_plan
        self.experiment = experiment
        self.verdict = verdict
        self.capability = capability


def pendulum_context() -> M4Context:
    return M4Context(
        CASE_MASS,
        parser_result=_claim(CASE_MASS),
        null_model=case_mass_null(),
        observables=case_mass_observable(),
        simulation_plan=case_mass_plan(),
        experiment=pendulum_experiment(),
        verdict=pendulum_verdict(),
    )


def quantitative_context() -> M4Context:
    return M4Context(
        CASE_QUANT,
        parser_result=_claim(CASE_QUANT),
        null_model=_null("H0 is y = 2*x + 1."),
        observables=_observable(
            h0="y follows 2*x + 1.",
            h1="y follows 2*x + 1 + 0.1*x*x.",
            difference=PredictedDifference.INCREASE,
            discriminating=True,
        ),
        simulation_plan=synthetic_plan(),
        experiment=quantitative_experiment(),
        verdict=quantitative_verdict(),
        capability=quantitative_capability(),
    )


def low_sensitivity_context() -> M4Context:
    return M4Context(
        CASE_LOW,
        parser_result=_claim(CASE_LOW),
        null_model=_null("H0 is y = 2*x + 1."),
        observables=_observable(
            h0="y follows 2*x + 1.",
            h1="y is larger by 0.001.",
            difference=PredictedDifference.INCREASE,
            discriminating=True,
        ),
        simulation_plan=_ready_curve(1.001, None),
        experiment=low_sensitivity_experiment(),
        verdict=low_sensitivity_verdict(),
        capability=low_sensitivity_capability(),
    )


def identical_context() -> M4Context:
    return M4Context(
        CASE_SAME,
        parser_result=_claim(CASE_SAME),
        null_model=_null("H0 is y = 2*x + 1."),
        observables=_observable(
            h0="y follows 2*x + 1.",
            h1="y follows 2*x + 1.",
            difference=PredictedDifference.ZERO,
            discriminating=False,
        ),
        simulation_plan=_ready_curve(1, None),
        experiment=identical_experiment(),
        verdict=identical_verdict(),
    )


def blocked_context() -> M4Context:
    return M4Context(
        CASE_B,
        parser_result=_claim(CASE_B),
        null_model=_null("No conventional quantity is identified."),
        observables=ObservableDesignResult(
            observables=[],
            blocking_issues=["the effect has no measurable quantity"],
            summary="No observable is defined.",
        ),
        simulation_plan=case_mass_plan(),
        experiment=blocked_experiment(),
    )


GOLDEN_EXPERIMENTS = {
    normalize_statement(CASE_MASS): pendulum_experiment,
    normalize_statement(CASE_QUANT): quantitative_experiment,
    normalize_statement(CASE_LOW): low_sensitivity_experiment,
    normalize_statement(CASE_SAME): identical_experiment,
    normalize_statement(CASE_B): blocked_experiment,
}

GOLDEN_VERDICTS = {
    normalize_statement(CASE_MASS): pendulum_verdict,
    normalize_statement(CASE_QUANT): quantitative_verdict,
    normalize_statement(CASE_LOW): low_sensitivity_verdict,
    normalize_statement(CASE_SAME): identical_verdict,
}
