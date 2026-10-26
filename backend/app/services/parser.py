"""Hypothesis parser. Stub mode is deterministic. Live mode does not fall back."""

from __future__ import annotations

from app.config import Settings
from app.prompts.parser import PARSER_SYSTEM_PROMPT, parser_user_prompt
from app.providers.meta import ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.claim import ClaimProvenance, EpistemicStatus, EvidenceOrigin
from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import (
    ClaimType,
    ExtractionConfidence,
    ExtractedAssumption,
    MissingDefinition,
    ParsedClaim,
    ParserResult,
)
from app.services.fixtures import GOLDEN_PARSERS, normalize_statement
from app.services.grounding import InventedEvidenceError, ensure_stated_evidence
from app.services.live import complete_structured
from app.services.modes import ExecutionMode


def parse_hypothesis(
    hypothesis: HypothesisInput,
    *,
    mode: ExecutionMode,
    settings: Settings,
    transport: ModelTransport | None = None,
) -> ParserResult:
    """Extract claims. Live failures stay live failures."""

    if mode is ExecutionMode.STUB:
        result = _stub_parse(hypothesis)
    elif mode is ExecutionMode.LIVE:
        result = complete_structured(
            settings,
            transport,
            system=PARSER_SYSTEM_PROMPT,
            user=parser_user_prompt(hypothesis.model_dump_json()),
            schema_name="ParserResult",
            model=ParserResult,
            reasoning_effort="minimal",
        )
    else:
        raise ValueError("unsupported execution mode")
    try:
        ensure_stated_evidence(hypothesis, result)
    except InventedEvidenceError as exc:
        raise ProviderResponseError(str(exc)) from None
    return result


def _stub_parse(hypothesis: HypothesisInput) -> ParserResult:
    builder = GOLDEN_PARSERS.get(normalize_statement(hypothesis.statement))
    if builder is None:
        result = _generic_parse(hypothesis)
    else:
        result = builder(hypothesis)
    return _include_user_context(result, hypothesis)


def _generic_parse(hypothesis: HypothesisInput) -> ParserResult:
    assumptions = [
        ExtractedAssumption(assumption_id=f"a{index}", statement=text, claim_ids=["c1"])
        for index, text in enumerate(hypothesis.assumptions, start=1)
    ]
    return ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement=hypothesis.statement,
                claim_type=ClaimType.EMPIRICAL,
                assumptions=list(hypothesis.assumptions),
                is_operational=False,
                missing_definitions=[
                    MissingDefinition(
                        statement="No controlled quantity or unit was stated.",
                        critical=True,
                    )
                ],
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.SPECULATIVE,
                confidence=ExtractionConfidence.LOW,
            )
        ],
        assumptions=assumptions,
        parser_notes=[
            "Stub mode found no golden hypothesis.",
            "No measurement, source, or parameter was added.",
        ],
    )


def _include_user_context(result: ParserResult, hypothesis: HypothesisInput) -> ParserResult:
    notes = list(result.parser_notes)
    if hypothesis.domain:
        notes.append("The supplied domain is user context, not evidence.")
    if hypothesis.context:
        notes.append("The supplied context is user context, not evidence.")
    existing = {item.statement for item in result.assumptions}
    assumptions = list(result.assumptions)
    next_index = len(assumptions) + 1
    claim_id = result.claims[0].claim_id
    for text in hypothesis.assumptions:
        if text in existing:
            continue
        assumptions.append(
            ExtractedAssumption(
                assumption_id=f"a{next_index}",
                statement=text,
                claim_ids=[claim_id],
            )
        )
        next_index += 1
    return result.model_copy(
        update={"parser_notes": notes, "assumptions": assumptions},
    )


