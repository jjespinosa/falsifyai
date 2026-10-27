"""Duffing and DQ-12 demo fixtures.

These are expected validated outputs for two full statements. They do not
add a stage and they do not branch on a substring inside the judge.
"""

from __future__ import annotations

from app.schemas.claim import ClaimProvenance, EpistemicStatus, EvidenceOrigin
from app.schemas.critic import (
    ConventionalExplanation,
    CritiqueIssue,
    IssueCategory,
    IssueSeverity,
    assemble_report,
)
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
    MissingDefinition,
    ParsedClaim,
    ParserResult,
)
from app.schemas.simulation import (
    IndependentVariable,
    ModelCurve,
    SimulationPlanResult,
    SimulationSpec,
)
from app.schemas.verdict import FalsificationVerdict
from app.services.fixtures import (
    GOLDEN_CLAIM_IDS,
    GOLDEN_CRITICS,
    GOLDEN_PARSERS,
    normalize_statement,
)
from app.services.m2_fixtures import GOLDEN_M2_CLAIM_IDS, GOLDEN_NULLS, GOLDEN_OBSERVABLES
from app.services.m3_fixtures import GOLDEN_PLANS, family_parameters
from app.services.m4_fixtures import GOLDEN_EXPERIMENTS, GOLDEN_VERDICTS

CASE_DUFFING = (
    "Synthetic Duffing benchmark — model prediction, not experimental data. "
    "Dimensionless weakly nonlinear control on 0 <= A <= 1. "
    "H0 harmonic oscillator: Omega(A) = 1. "
    "H1 weak Duffing approximation: Omega(A) = 1 + 0.075 * A^2. "
    "Explicit benchmark measurement uncertainty sigma_Omega = 0.01 for Omega."
)

CASE_DQ12 = (
    "After standard decoherence channels are modeled and controlled, a DQ-12 "
    "hypothesis proposes that an entangled two-system experiment may contain an "
    "additional decoherence contribution associated with an underlying "
    "twelve-dimensional separation rather than solely with measured "
    "three-dimensional separation."
)

DUFFING_NOTICE = "Synthetic Duffing benchmark — model prediction, not experimental data."
DQ12_NOTICE = "Speculative hypothesis — not established physics."

DQ12_NEXT = (
    "Define an operational proxy for the twelve-dimensional separation from "
    "experimentally accessible quantities, a quantitative relationship between "
    "that separation and the predicted decoherence contribution, parameter bounds "
    "or a minimum effect size, and a prediction that differs from conventional "
    "decoherence models."
)

_D12_QUESTION = (
    "How is the twelve-dimensional separation d12 defined, inferred, or "
    "controlled from experimentally accessible quantities?"
)


def register_m6_fixtures() -> None:
    """Point the two M6 statements at stub builders. Repeated calls are harmless."""

    duffing = normalize_statement(CASE_DUFFING)
    dq12 = normalize_statement(CASE_DQ12)
    GOLDEN_PARSERS[duffing] = _duffing_parser
    GOLDEN_CRITICS[duffing] = _duffing_critic
    GOLDEN_CLAIM_IDS[duffing] = {"c1"}
    GOLDEN_NULLS[duffing] = _duffing_null
    GOLDEN_OBSERVABLES[duffing] = _duffing_observable
    GOLDEN_M2_CLAIM_IDS[duffing] = {"c1"}
    GOLDEN_PLANS[duffing] = _duffing_plan
    GOLDEN_EXPERIMENTS[duffing] = _duffing_experiment
    GOLDEN_VERDICTS[duffing] = _duffing_verdict
    GOLDEN_PARSERS[dq12] = _dq12_parser
    GOLDEN_CRITICS[dq12] = _dq12_critic
    GOLDEN_CLAIM_IDS[dq12] = {"c1"}
    GOLDEN_NULLS[dq12] = _dq12_null
    GOLDEN_OBSERVABLES[dq12] = _dq12_observable
    GOLDEN_M2_CLAIM_IDS[dq12] = {"c1"}
    GOLDEN_PLANS[dq12] = _dq12_plan
    GOLDEN_VERDICTS[dq12] = _dq12_verdict


def _duffing_parser(hypothesis: HypothesisInput) -> ParserResult:
    return ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement=hypothesis.statement,
                claim_type=ClaimType.PREDICTIVE,
                variables=[
                    ClaimVariable(name="amplitude A", defined=True),
                    ClaimVariable(name="frequency ratio Omega", defined=True),
                ],
                is_operational=True,
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.HYPOTHESIS,
                confidence=ExtractionConfidence.HIGH,
            )
        ],
        parser_notes=["The stated curves and uncertainty identify a quantitative comparison."],
    )


def _duffing_critic() -> object:
    return assemble_report(
        issues=[
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.MINOR,
                category=IssueCategory.HIDDEN_ASSUMPTION,
                statement="The weak-nonlinearity approximation is limited to the stated domain.",
                affected_claim_ids=["c1"],
                evidence_basis="The hypothesis states the weak Duffing approximation and the domain.",
                blocking=False,
            )
        ],
        conventional_explanations=[
            ConventionalExplanation(
                explanation_id="e1",
                statement="H0 is the harmonic oscillator with Omega(A) = 1.",
                affected_claim_ids=["c1"],
                evidence_basis="The hypothesis states the harmonic curve.",
            )
        ],
        summary="Both curves and the benchmark uncertainty are stated.",
    )


def _duffing_null() -> NullModelResult:
    return NullModelResult(
        models=[
            NullModel(
                model_id="h0",
                description="Harmonic oscillator with amplitude-independent frequency Omega(A) = 1.",
                target_claim_ids=["c1"],
                equations=[
                    SourcedStatement(
                        statement="Omega(A) = 1",
                        basis=KnowledgeBasis.USER_SUPPLIED,
                    )
                ],
                can_mimic_claim=False,
                mimicry_reason="A constant frequency does not reproduce the stated amplitude-squared shift.",
                basis=KnowledgeBasis.USER_SUPPLIED,
            )
        ],
        summary="H0 is the stated amplitude-independent harmonic frequency.",
    )


def _duffing_observable() -> ObservableDesignResult:
    return ObservableDesignResult(
        observables=[
            ObservableCandidate(
                observable_id="o1",
                name="oscillation frequency ratio",
                symbol="Omega",
                definition="Oscillation frequency ratio Omega versus amplitude A.",
                units="1",
                measurement_method="Read Omega at a stated amplitude. This benchmark is not a laboratory instrument.",
                target_claim_ids=["c1"],
                h1_prediction="Omega(A) = 1 + 0.075 * A^2",
                h0_prediction="Omega(A) = 1",
                predicted_difference=PredictedDifference.INCREASE,
                required_controls=["domain 0 <= A <= 1"],
                known_confounders=[],
                blocking_missing_definitions=[],
                discriminating=True,
            )
        ],
        summary="Omega versus A separates the stated harmonic and weak Duffing curves.",
    )


def duffing_spec() -> SimulationSpec:
    """Registered constant and quadratic families. Coefficients are the stated ones."""

    return SimulationSpec(
        simulation_id="sim1",
        observable_id="o1",
        template="static_curve",
        independent_variable=IndependentVariable(name="A", units="1", min=0, max=1, points=11),
        h0=ModelCurve(family="constant", parameters=family_parameters(value=1)),
        h1=ModelCurve(
            family="quadratic",
            parameters=family_parameters(quadratic=0.075, slope=0, intercept=1),
        ),
        outputs=["h0", "h1", "delta"],
        assumptions=["Weak-nonlinearity benchmark on the stated domain."],
        seed=1,
        sweep=None,
    )


def _duffing_plan() -> SimulationPlanResult:
    return SimulationPlanResult(
        status="ready",
        observable_id="o1",
        spec=duffing_spec(),
        blocking_missing_definitions=[],
        assumptions=["Weak-nonlinearity benchmark on the stated domain."],
        summary="The stated harmonic and weak Duffing curves are registered numerical families.",
    )


def _duffing_experiment() -> ExperimentPlanResult:
    plan = ExperimentPlan(
        experiment_id="exp1",
        objective="Compare Omega(A) with the harmonic value on the stated amplitude domain.",
        target_claim_ids=["c1"],
        observable_ids=["o1"],
        independent_variables=[ExperimentVariable(name="A", units="1", capability="user_supplied")],
        measured_variables=[
            ExperimentVariable(name="Omega", units="1", capability="required")
        ],
        controlled_variables=[
            ExperimentVariable(name="stated amplitude domain", units="1", capability="user_supplied")
        ],
        control_groups=["the same stated amplitude values"],
        parameter_scan=[
            ParameterScan(name="A", units="1", lower=0, upper=1, status="defined")
        ],
        required_resolution=RequiredResolution(
            observable_id="o1",
            value=0.01,
            units="1",
            basis="The benchmark states sigma_Omega = 0.01.",
            status="defined",
        ),
        confounders=[],
        procedure_outline=[
            "Read Omega at the stated amplitudes.",
            "Compare each reading with the harmonic value Omega(A) = 1.",
        ],
        stop_conditions=["Stop if the stated amplitude domain cannot be covered."],
        falsifier_candidate=(
            "Readings that stay within the stated uncertainty of Omega(A) = 1 "
            "would miss the stated weak Duffing shift."
        ),
        limitations=["Synthetic benchmark prediction, not experimental data."],
        safety_notes=[SAFETY_NOTE],
    )
    return ExperimentPlanResult(
        status="ready",
        experiment=plan,
        blocking_missing_definitions=[],
        summary="The stated uncertainty defines a resolution for Omega versus A.",
    )


def _duffing_verdict() -> FalsificationVerdict:
    return FalsificationVerdict(
        status="TESTABLE",
        primary_reason=(
            "At the upper stated amplitude the model separation is 0.075 and the "
            "stated uncertainty is 0.01, so a finite comparison is defined."
        ),
        falsifier=(
            "An Omega reading on the stated domain that stays within the stated "
            "uncertainty of the harmonic value would miss the stated weak Duffing shift."
        ),
        required_next_definition=None,
        delta_over_sigma=7.5,
        limitations=["Synthetic benchmark prediction, not experimental data."],
        evidence_refs=["c1", "h0", "o1", "exp1", "sim1"],
    )


def _dq12_parser(hypothesis: HypothesisInput) -> ParserResult:
    return ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement=hypothesis.statement,
                claim_type=ClaimType.PREDICTIVE,
                variables=[
                    ClaimVariable(name="decoherence", defined=True),
                    ClaimVariable(name="three-dimensional separation", defined=True),
                    ClaimVariable(name="twelve-dimensional separation", defined=False),
                ],
                is_operational=False,
                missing_definitions=[
                    MissingDefinition(statement=_D12_QUESTION, critical=True)
                ],
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.SPECULATIVE,
                confidence=ExtractionConfidence.LOW,
            )
        ],
        parser_notes=["The twelve-dimensional separation has no operational map in the statement."],
    )


def _dq12_critic() -> object:
    return assemble_report(
        issues=[
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.BLOCKING,
                category=IssueCategory.UNDEFINED_VARIABLE,
                statement=_D12_QUESTION,
                affected_claim_ids=["c1"],
                evidence_basis="The statement names the separation and does not define it.",
                blocking=True,
            )
        ],
        conventional_explanations=[
            ConventionalExplanation(
                explanation_id="e1",
                statement=(
                    "Ordinary decoherence and experimental effects can account for "
                    "observed decoherence without a twelve-dimensional contribution."
                ),
                affected_claim_ids=["c1"],
                evidence_basis="The statement says standard decoherence channels are the comparison.",
            )
        ],
        required_clarifications=[DQ12_NEXT],
        summary="The hidden separation is not operational, so the claim is not yet a finite test.",
    )


def _dq12_null() -> NullModelResult:
    return NullModelResult(
        models=[
            NullModel(
                model_id="h0",
                description=(
                    "Ordinary decoherence and experimental or systematic effects explain "
                    "the observed decoherence without a twelve-dimensional contribution."
                ),
                target_claim_ids=["c1"],
                assumptions=[
                    SourcedStatement(
                        statement="Standard decoherence channels are the conventional account.",
                        basis=KnowledgeBasis.STANDARD_KNOWLEDGE,
                    )
                ],
                known_confounders=[
                    "environmental decoherence",
                    "thermal effects",
                    "electromagnetic noise",
                    "calibration drift",
                    "state-preparation differences",
                    "detection and systematic effects",
                ],
                can_mimic_claim=True,
                mimicry_reason=(
                    "Those conventional channels can reproduce an apparent extra "
                    "decoherence without a twelve-dimensional contribution."
                ),
                limitations=[_D12_QUESTION],
                basis=KnowledgeBasis.STANDARD_KNOWLEDGE,
                blocking_missing_definitions=[_D12_QUESTION],
            )
        ],
        summary="H0 is ordinary decoherence plus experimental effects.",
    )


def _dq12_observable() -> ObservableDesignResult:
    return ObservableDesignResult(
        observables=[
            ObservableCandidate(
                observable_id="o1",
                name="residual decoherence",
                symbol="residual",
                definition=(
                    "Residual decoherence after conventional channels are modeled and "
                    "controlled. An unexplained residual is not evidence for the claim."
                ),
                units="1",
                measurement_method=(
                    "Record decoherence after the stated conventional channels are controlled."
                ),
                target_claim_ids=["c1"],
                h1_prediction=(
                    "An additional decoherence contribution associated with an undefined "
                    "twelve-dimensional separation."
                ),
                h0_prediction=(
                    "Ordinary decoherence and experimental effects account for the residual."
                ),
                predicted_difference=PredictedDifference.QUALITATIVE_DIFFERENCE,
                required_controls=[
                    "standard decoherence channels modeled and controlled",
                ],
                known_confounders=[],
                blocking_missing_definitions=[],
                non_blocking_missing_definitions=[_D12_QUESTION],
                discriminating=False,
            )
        ],
        blocking_issues=[
            "The residual does not discriminate until the twelve-dimensional separation "
            "has an operational definition and a quantitative prediction that differs "
            "from conventional decoherence."
        ],
        summary=(
            "Residual decoherence can be described in principle. An unexplained residual "
            "is not evidence for the twelve-dimensional contribution."
        ),
    )


def _dq12_plan() -> SimulationPlanResult:
    return SimulationPlanResult(
        status="blocked",
        observable_id="o1",
        spec=None,
        blocking_missing_definitions=[
            "No quantitative relationship between the twelve-dimensional separation "
            "and a decoherence contribution was supplied."
        ],
        assumptions=[],
        summary="Simulation is blocked. No quantitative law was invented.",
    )


def _dq12_verdict() -> FalsificationVerdict:
    return FalsificationVerdict(
        status="NOT_YET_FALSIFIABLE",
        primary_reason=(
            "The statement does not operationally define the twelve-dimensional "
            "separation, and an unexplained residual is not evidence for that contribution."
        ),
        falsifier=(
            "A stated quantitative contribution that differs from ordinary decoherence "
            "could be missed or found by a residual measurement. No such contribution is stated."
        ),
        required_next_definition=DQ12_NEXT,
        delta_over_sigma=None,
        limitations=["Speculative hypothesis. This is not established physics."],
        evidence_refs=["c1", "h0", "o1", "exp1"],
    )
