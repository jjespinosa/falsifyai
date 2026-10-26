"""Adversarial critic. Stub mode is deterministic. Live mode does not fall back."""

from __future__ import annotations

from app.config import Settings
from app.prompts.critic import CRITIC_SYSTEM_PROMPT, critic_user_prompt
from app.providers.meta import ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.critic import (
    CritiqueIssue,
    CritiqueReport,
    IssueCategory,
    IssueSeverity,
    assemble_report,
    require_known_claim_ids,
)
from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import ParserResult
from app.services.fixtures import GOLDEN_CLAIM_IDS, GOLDEN_CRITICS, normalize_statement
from app.services.live import complete_structured
from app.services.modes import ExecutionMode


def critique_hypothesis(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    *,
    mode: ExecutionMode,
    settings: Settings,
    transport: ModelTransport | None = None,
) -> CritiqueReport:
    """Review parsed claims. A live failure is returned as a provider error."""

    if mode is ExecutionMode.STUB:
        report = _stub_critique(hypothesis, parser_result)
    elif mode is ExecutionMode.LIVE:
        report = complete_structured(
            settings,
            transport,
            system=CRITIC_SYSTEM_PROMPT,
            user=critic_user_prompt(
                hypothesis_payload=hypothesis.model_dump_json(),
                parser_payload=parser_result.model_dump_json(),
            ),
            schema_name="CritiqueReport",
            model=CritiqueReport,
        )
    else:
        raise ValueError("unsupported execution mode")
    try:
        require_known_claim_ids(report, {claim.claim_id for claim in parser_result.claims})
    except ValueError:
        raise ProviderResponseError(
            "The critique refers to a claim id that the parser did not extract."
        ) from None
    return report


def _stub_critique(hypothesis: HypothesisInput, parser_result: ParserResult) -> CritiqueReport:
    key = normalize_statement(hypothesis.statement)
    builder = GOLDEN_CRITICS.get(key)
    claim_ids = {claim.claim_id for claim in parser_result.claims}
    expected = GOLDEN_CLAIM_IDS.get(key)
    if builder is not None and expected is not None and expected <= claim_ids:
        return builder()
    return _generic_critique(parser_result)


def _generic_critique(parser_result: ParserResult) -> CritiqueReport:
    non_operational = [claim.claim_id for claim in parser_result.claims if not claim.is_operational]
    if non_operational:
        issues = [
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.BLOCKING,
                category=IssueCategory.NON_OPERATIONAL_CLAIM,
                statement=(
                    "At least one claim is not connected to a controlled, measured, "
                    "or defined quantity."
                ),
                affected_claim_ids=non_operational,
                evidence_basis="The parser marked the claim non-operational or left a quantity undefined.",
                blocking=True,
            )
        ]
        clarifications = [
            item
            for claim in parser_result.claims
            if not claim.is_operational
            for item in claim.missing_definitions
        ]
        summary = (
            "The parsed claims are not experimentally testable until the missing "
            "quantities are defined. No supporting measurement was added."
        )
    else:
        issues = [
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.MINOR,
                category=IssueCategory.MISSING_CONTROL,
                statement="The stub critic sees operational claims and no stated comparison condition.",
                affected_claim_ids=[claim.claim_id for claim in parser_result.claims],
                evidence_basis="Stub mode does not invent a control condition.",
                blocking=False,
            )
        ]
        clarifications = []
        summary = (
            "The claims name defined quantities. Stub mode does not treat that as "
            "support, and it does not invent a discriminating comparison."
        )
    return assemble_report(
        issues=issues,
        required_clarifications=clarifications,
        summary=summary,
    )
