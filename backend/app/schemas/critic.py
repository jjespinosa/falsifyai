"""Adversarial critique of a parsed hypothesis."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.hypothesis import HypothesisInput
from app.schemas.identifiers import EXPLANATION_ID_PATTERN, ISSUE_ID_PATTERN, ClaimId
from app.schemas.parser import ParserResult


class IssueSeverity(str, Enum):
    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"


class IssueCategory(str, Enum):
    UNDEFINED_VARIABLE = "undefined_variable"
    DIMENSIONAL_INCONSISTENCY = "dimensional_inconsistency"
    CAUSAL_AMBIGUITY = "causal_ambiguity"
    NON_OPERATIONAL_CLAIM = "non_operational_claim"
    HIDDEN_ASSUMPTION = "hidden_assumption"
    PARAMETER_DEGENERACY = "parameter_degeneracy"
    CIRCULAR_DEFINITION = "circular_definition"
    MISSING_CONTROL = "missing_control"
    CONVENTIONAL_EXPLANATION = "conventional_explanation"
    UNSUPPORTED_MECHANISM = "unsupported_mechanism"
    NON_DISCRIMINATING_PREDICTION = "non_discriminating_prediction"


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class CritiqueIssue(BaseModel):
    """One reason a claim is not yet experimentally testable, or only weakly so."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(pattern=ISSUE_ID_PATTERN)
    severity: IssueSeverity
    category: IssueCategory
    statement: str = Field(min_length=1, max_length=1_000)
    affected_claim_ids: list[ClaimId] = Field(min_length=1)
    evidence_basis: str = Field(min_length=1, max_length=500)
    blocking: bool

    @field_validator("issue_id", "statement", "evidence_basis", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _strip_text(value)

    @model_validator(mode="after")
    def _blocking_matches_severity(self) -> CritiqueIssue:
        if (self.severity is IssueSeverity.BLOCKING) != self.blocking:
            raise ValueError("blocking is true only when severity is blocking")
        return self


class ConventionalExplanation(BaseModel):
    """A standard account that could produce the same observation."""

    model_config = ConfigDict(extra="forbid")

    explanation_id: str = Field(pattern=EXPLANATION_ID_PATTERN)
    statement: str = Field(min_length=1, max_length=1_000)
    affected_claim_ids: list[ClaimId] = Field(min_length=1)
    evidence_basis: str = Field(min_length=1, max_length=500)

    @field_validator("explanation_id", "statement", "evidence_basis", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _strip_text(value)

class CritiqueReport(BaseModel):
    """A skeptical review. It does not award support to the hypothesis."""

    model_config = ConfigDict(extra="forbid")

    issues: list[CritiqueIssue]
    blocking_issues: list[CritiqueIssue]
    major_issues: list[CritiqueIssue]
    minor_issues: list[CritiqueIssue]
    conventional_explanations: list[ConventionalExplanation] = Field(default_factory=list)
    required_clarifications: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=2_000)

    @field_validator("summary", mode="before")
    @classmethod
    def _strip_summary(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("required_clarifications", mode="before")
    @classmethod
    def _strip_clarifications(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @field_validator("required_clarifications")
    @classmethod
    def _clarifications_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("required_clarifications must not contain blank items")
        return value

    @model_validator(mode="after")
    def _buckets_match_issues(self) -> CritiqueReport:
        issue_ids = [issue.issue_id for issue in self.issues]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("issue_id values must be unique")
        explanation_ids = [item.explanation_id for item in self.conventional_explanations]
        if len(explanation_ids) != len(set(explanation_ids)):
            raise ValueError("explanation_id values must be unique")
        expected = {
            IssueSeverity.BLOCKING: self.blocking_issues,
            IssueSeverity.MAJOR: self.major_issues,
            IssueSeverity.MINOR: self.minor_issues,
        }
        for severity, bucket in expected.items():
            actual_ids = [issue.issue_id for issue in self.issues if issue.severity is severity]
            bucket_ids = [issue.issue_id for issue in bucket]
            if actual_ids != bucket_ids:
                raise ValueError("issue buckets must list the issues of that severity, in order")
        return self


class CritiqueInput(BaseModel):
    """Request body for the critic. The caller supplies the parser output."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisInput
    parser_result: ParserResult


def require_known_claim_ids(report: CritiqueReport, claim_ids: set[str]) -> None:
    """Reject critique targets that the parser did not extract."""

    for issue in report.issues:
        unknown = [claim_id for claim_id in issue.affected_claim_ids if claim_id not in claim_ids]
        if unknown:
            raise ValueError("affected_claim_ids must refer to parsed claims")
    for explanation in report.conventional_explanations:
        unknown = [
            claim_id for claim_id in explanation.affected_claim_ids if claim_id not in claim_ids
        ]
        if unknown:
            raise ValueError("affected_claim_ids must refer to parsed claims")


def assemble_report(
    *,
    issues: list[CritiqueIssue],
    conventional_explanations: list[ConventionalExplanation] | None = None,
    required_clarifications: list[str] | None = None,
    summary: str,
) -> CritiqueReport:
    """Build a report whose severity buckets match the issue list."""

    return CritiqueReport(
        issues=issues,
        blocking_issues=[issue for issue in issues if issue.severity is IssueSeverity.BLOCKING],
        major_issues=[issue for issue in issues if issue.severity is IssueSeverity.MAJOR],
        minor_issues=[issue for issue in issues if issue.severity is IssueSeverity.MINOR],
        conventional_explanations=conventional_explanations or [],
        required_clarifications=required_clarifications or [],
        summary=summary,
    )
