"""Schema tests for parser output."""

import json

import pytest
from pydantic import ValidationError

from app.prompts.parser import PARSER_SYSTEM_PROMPT
from app.providers.schema_json import strict_json_schema
from app.schemas.claim import ClaimProvenance, EvidenceOrigin
from app.schemas.parser import (
    ClaimType,
    ExtractionConfidence,
    ParsedClaim,
    ParserResult,
)
from app.services.fixtures import CASE_A, case_a_parser
from app.schemas.hypothesis import HypothesisInput


def test_parser_result_accepts_an_operational_measurement() -> None:
    result = case_a_parser(HypothesisInput(statement=CASE_A))

    assert result.claims[0].is_operational is True
    assert result.claims[0].provenance.origin is EvidenceOrigin.MEASURED
    assert result.claims[0].provenance.value == 2.007
    assert "You are the Hypothesis Parser inside FalsifyAI." in PARSER_SYSTEM_PROMPT


def test_parser_schema_rejects_a_speculative_operational_claim() -> None:
    with pytest.raises(ValidationError):
        ParsedClaim(
            claim_id="c1",
            statement="A named effect occurs.",
            claim_type=ClaimType.MECHANISTIC,
            is_operational=True,
            provenance=ClaimProvenance(origin=EvidenceOrigin.SPECULATIVE),
            confidence=ExtractionConfidence.LOW,
        )


def test_parser_schema_rejects_duplicate_claim_ids() -> None:
    claim = ParsedClaim(
        claim_id="c1",
        statement="A named effect occurs.",
        claim_type=ClaimType.EMPIRICAL,
        is_operational=False,
        missing_definitions=["no quantity was stated"],
        provenance=ClaimProvenance(origin=EvidenceOrigin.SPECULATIVE),
        confidence=ExtractionConfidence.LOW,
    )

    with pytest.raises(ValidationError):
        ParserResult(claims=[claim, claim.model_copy(update={"statement": "Another wording."})])


def test_structured_output_schema_has_no_local_refs() -> None:
    schema = strict_json_schema(ParserResult)

    assert "$ref" not in json.dumps(schema)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
