"""Schema tests for critique reports."""

import pytest
from pydantic import ValidationError

from app.prompts.critic import CRITIC_SYSTEM_PROMPT
from app.schemas.critic import (
    CritiqueIssue,
    IssueCategory,
    IssueSeverity,
    assemble_report,
    require_known_claim_ids,
)
from app.services.fixtures import case_b_critic


def test_critique_report_buckets_match_severity() -> None:
    report = case_b_critic()

    assert [issue.severity for issue in report.blocking_issues] == [
        IssueSeverity.BLOCKING,
        IssueSeverity.BLOCKING,
    ]
    assert report.major_issues == []
    assert report.minor_issues == []
    assert "You are the Adversarial Scientific Critic inside FalsifyAI." in CRITIC_SYSTEM_PROMPT


def test_severity_enum_rejects_an_unknown_level() -> None:
    with pytest.raises(ValidationError):
        CritiqueIssue(
            issue_id="i1",
            severity="urgent",
            category=IssueCategory.NON_OPERATIONAL_CLAIM,
            statement="The claim is not testable.",
            affected_claim_ids=["c1"],
            evidence_basis="No quantity was stated.",
            blocking=True,
        )


def test_blocking_flag_must_match_severity() -> None:
    with pytest.raises(ValidationError):
        CritiqueIssue(
            issue_id="i1",
            severity=IssueSeverity.MAJOR,
            category=IssueCategory.HIDDEN_ASSUMPTION,
            statement="An assumption is doing the work of a measurement.",
            affected_claim_ids=["c1"],
            evidence_basis="The text labels the step as an assumption.",
            blocking=True,
        )


def test_unknown_affected_claim_id_is_rejected() -> None:
    report = assemble_report(
        issues=[
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.MINOR,
                category=IssueCategory.MISSING_CONTROL,
                statement="No comparison was stated.",
                affected_claim_ids=["c999"],
                evidence_basis="The parser did not extract c999.",
                blocking=False,
            )
        ],
        summary="The target claim is not in the parser result.",
    )

    with pytest.raises(ValueError, match="affected_claim_ids"):
        require_known_claim_ids(report, {"c1"})
