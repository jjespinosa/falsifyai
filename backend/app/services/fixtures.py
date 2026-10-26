"""Deterministic parser and critic fixtures for stub mode.

The three cases are the golden hypotheses. No fixture adds a number or a
source that its hypothesis text does not already contain.
"""

from app.schemas.claim import ClaimProvenance, EpistemicStatus, EvidenceOrigin
from app.schemas.critic import (
    ConventionalExplanation,
    CritiqueIssue,
    CritiqueReport,
    IssueCategory,
    IssueSeverity,
    assemble_report,
)
from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import (
    ClaimType,
    ClaimVariable,
    ExtractedAssumption,
    ExtractionConfidence,
    MissingDefinition,
    ParsedClaim,
    ParserResult,
    UndefinedTerm,
)

CASE_A = (
    "A simple pendulum of length 1.000 m has an oscillation period of 2.007 s, "
    "measured with a photogate at sea level."
)
CASE_B = "Quantum biofield resonance improves systemic healing."
CASE_C = (
    "Tomato plants grow faster beside this speaker because the music "
    "transfers vital energy into their cells."
)


def normalize_statement(statement: str) -> str:
    return " ".join(statement.split())


def case_a_parser(hypothesis: HypothesisInput) -> ParserResult:
    del hypothesis
    return ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement=CASE_A,
                claim_type=ClaimType.EMPIRICAL,
                variables=[
                    ClaimVariable(name="length", unit="m", defined=True),
                    ClaimVariable(name="oscillation period", unit="s", defined=True),
                ],
                is_operational=True,
                provenance=ClaimProvenance(
                    origin=EvidenceOrigin.MEASURED,
                    observable="oscillation period",
                    value=2.007,
                    unit="s",
                ),
                epistemic_status=EpistemicStatus.ESTABLISHED,
                confidence=ExtractionConfidence.HIGH,
            )
        ],
        assumptions=[
            ExtractedAssumption(
                assumption_id="a1",
                statement=(
                    "The photogate reading named by the user is the oscillation "
                    "period of that pendulum."
                ),
                claim_ids=["c1"],
            )
        ],
        parser_notes=[
            "One measurement claim was extracted.",
            "The user stated no uncertainty, so none was added.",
        ],
    )


def case_b_parser(hypothesis: HypothesisInput) -> ParserResult:
    del hypothesis
    return ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement=CASE_B,
                claim_type=ClaimType.MECHANISTIC,
                variables=[
                    ClaimVariable(name="quantum biofield resonance", defined=False),
                    ClaimVariable(name="systemic healing", defined=False),
                ],
                is_operational=False,
                missing_definitions=[
                    MissingDefinition(
                        statement="quantum biofield resonance has no stated quantity or unit",
                        critical=True,
                    ),
                    MissingDefinition(
                        statement="systemic healing has no stated quantity or unit",
                        critical=True,
                    ),
                ],
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.SPECULATIVE,
                confidence=ExtractionConfidence.LOW,
            )
        ],
        undefined_terms=[
            UndefinedTerm(
                term="quantum biofield resonance",
                reason="The hypothesis names no measurement procedure or unit.",
                claim_ids=["c1"],
            ),
            UndefinedTerm(
                term="systemic healing",
                reason="The hypothesis names no observable outcome or unit.",
                claim_ids=["c1"],
            ),
        ],
        parser_notes=[
            "No measurement, citation, or controlled quantity was stated, so none was added."
        ],
    )


def case_c_parser(hypothesis: HypothesisInput) -> ParserResult:
    del hypothesis
    return ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement="Tomato plants grow faster beside this speaker.",
                claim_type=ClaimType.EMPIRICAL,
                variables=[
                    ClaimVariable(name="plant growth", defined=False),
                    ClaimVariable(name="speaker exposure", defined=False),
                ],
                is_operational=False,
                missing_definitions=[
                    MissingDefinition(
                        statement="growth has no stated measure or time window",
                        critical=True,
                    ),
                    MissingDefinition(
                        statement="beside this speaker has no stated distance or dose",
                        critical=True,
                    ),
                ],
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.HYPOTHESIS,
                confidence=ExtractionConfidence.MEDIUM,
            ),
            ParsedClaim(
                claim_id="c2",
                statement="The music transfers vital energy into the cells of the tomato plants.",
                claim_type=ClaimType.MECHANISTIC,
                variables=[ClaimVariable(name="vital energy", defined=False)],
                is_operational=False,
                missing_definitions=[
                    MissingDefinition(
                        statement="vital energy has no stated physical quantity or unit",
                        critical=True,
                    )
                ],
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.SPECULATIVE,
                confidence=ExtractionConfidence.LOW,
            ),
        ],
        undefined_terms=[
            UndefinedTerm(
                term="grow faster",
                reason="The hypothesis names no growth measure or duration.",
                claim_ids=["c1"],
            ),
            UndefinedTerm(
                term="vital energy",
                reason="The hypothesis names no physical quantity or unit.",
                claim_ids=["c2"],
            ),
        ],
        parser_notes=[
            "The growth effect and the vital-energy mechanism were kept as two claims.",
            "No growth measurement was stated, so none was added.",
        ],
    )


def case_a_critic() -> CritiqueReport:
    return assemble_report(
        issues=[
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.MINOR,
                category=IssueCategory.MISSING_CONTROL,
                statement=(
                    "The text reports one measured period and one length. "
                    "It states no comparison condition and no repeat count."
                ),
                affected_claim_ids=["c1"],
                evidence_basis=(
                    "The hypothesis states a single photogate period and a length, "
                    "and it states no second condition."
                ),
                blocking=False,
            )
        ],
        summary=(
            "The claim names a measured observable with units. "
            "It is operational as a single measurement. "
            "It does not yet say what comparison would challenge it."
        ),
    )


def case_b_critic() -> CritiqueReport:
    return assemble_report(
        issues=[
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.BLOCKING,
                category=IssueCategory.UNDEFINED_VARIABLE,
                statement=(
                    "Quantum biofield resonance and systemic healing are not tied "
                    "to a quantity, a unit, or a measurement procedure."
                ),
                affected_claim_ids=["c1"],
                evidence_basis="The hypothesis states neither a number nor a unit.",
                blocking=True,
            ),
            CritiqueIssue(
                issue_id="i2",
                severity=IssueSeverity.BLOCKING,
                category=IssueCategory.NON_OPERATIONAL_CLAIM,
                statement="The claim cannot be compared with an observation until both terms are defined.",
                affected_claim_ids=["c1"],
                evidence_basis="The parser marked the only claim non-operational.",
                blocking=True,
            ),
        ],
        required_clarifications=[
            "Define quantum biofield resonance as a quantity with a unit and a measurement procedure.",
            "Define systemic healing as an observable with a unit.",
        ],
        summary=(
            "The sentence names no controlled, measured, or defined quantity, "
            "so it is not experimentally testable yet."
        ),
    )


def case_c_critic() -> CritiqueReport:
    explanation = ConventionalExplanation(
        explanation_id="e1",
        statement=(
            "Light, temperature, water, and airflow can change plant growth and can "
            "differ beside a speaker. Audible sound can also move air. Those ordinary "
            "factors can mimic a growth change without vital energy."
        ),
        affected_claim_ids=["c1", "c2"],
        evidence_basis=(
            "The hypothesis does not report light, temperature, water, or airflow, "
            "which are ordinary controls on plant growth."
        ),
    )
    return assemble_report(
        issues=[
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.BLOCKING,
                category=IssueCategory.NON_OPERATIONAL_CLAIM,
                statement="Grow faster names no growth measure and no time window.",
                affected_claim_ids=["c1"],
                evidence_basis="The hypothesis does not state a height, mass, area, or duration.",
                blocking=True,
            ),
            CritiqueIssue(
                issue_id="i2",
                severity=IssueSeverity.MAJOR,
                category=IssueCategory.UNSUPPORTED_MECHANISM,
                statement="Vital energy is not identified with a physical quantity the text defines.",
                affected_claim_ids=["c2"],
                evidence_basis="The hypothesis names vital energy and states no unit or instrument.",
                blocking=False,
            ),
            CritiqueIssue(
                issue_id="i3",
                severity=IssueSeverity.MAJOR,
                category=IssueCategory.CONVENTIONAL_EXPLANATION,
                statement=explanation.statement,
                affected_claim_ids=["c1", "c2"],
                evidence_basis=explanation.evidence_basis,
                blocking=False,
            ),
        ],
        conventional_explanations=[explanation],
        required_clarifications=[
            "Define growth as a measured quantity and name the time window.",
            "State the light, temperature, water, and airflow beside the speaker and away from it.",
        ],
        summary=(
            "The growth sentence is not yet a measurement, and the vital-energy "
            "mechanism is undefined. Ordinary growing conditions can mimic a change "
            "in growth, so those conditions have to be separated before the mechanism "
            "can be tested. The mechanism is not dismissed for being unfamiliar."
        ),
    )


GOLDEN_PARSERS = {
    normalize_statement(CASE_A): case_a_parser,
    normalize_statement(CASE_B): case_b_parser,
    normalize_statement(CASE_C): case_c_parser,
}

GOLDEN_CRITICS = {
    normalize_statement(CASE_A): case_a_critic,
    normalize_statement(CASE_B): case_b_critic,
    normalize_statement(CASE_C): case_c_critic,
}

GOLDEN_CLAIM_IDS = {
    normalize_statement(CASE_A): {"c1"},
    normalize_statement(CASE_B): {"c1"},
    normalize_statement(CASE_C): {"c1", "c2"},
}
