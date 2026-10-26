"""Schema tests for parser output."""

import json

import pytest
from pydantic import ValidationError

from app.prompts.parser import PARSER_SYSTEM_PROMPT
from app.providers.schema_json import strict_json_schema, strict_subset_issues
from app.schemas.critic import CritiqueReport
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


def _defined_claim(**updates: object) -> ParsedClaim:
    payload = {
        "claim_id": "c1",
        "statement": "Increasing length increases the period.",
        "claim_type": ClaimType.CAUSAL,
        "variables": [{"name": "length", "unit": "m", "defined": True}],
        "is_operational": True,
        "provenance": {"origin": "assumed"},
        "epistemic_status": "speculative",
        "confidence": "medium",
    }
    payload.update(updates)
    return ParsedClaim.model_validate(payload)


def test_identifier_case_is_rejected_and_pattern_is_in_the_schema() -> None:
    from app.schemas.identifiers import ASSUMPTION_ID_PATTERN, CLAIM_ID_PATTERN, REGISTERED_ID_PATTERN
    from app.schemas.parser import ExtractedAssumption

    assert _defined_claim().claim_id == "c1"
    with pytest.raises(ValidationError):
        _defined_claim(claim_id="C1")
    ExtractedAssumption(assumption_id="a1", statement="Small angle.", claim_ids=["c1"])
    with pytest.raises(ValidationError):
        ExtractedAssumption(assumption_id="A1", statement="Small angle.", claim_ids=["c1"])

    sent = strict_json_schema(ParserResult)
    claim = sent["properties"]["claims"]["items"]["properties"]
    assert claim["claim_id"]["pattern"] == CLAIM_ID_PATTERN
    assumption = sent["properties"]["assumptions"]["items"]["properties"]
    assert assumption["assumption_id"]["pattern"] == ASSUMPTION_ID_PATTERN
    provenance = claim["provenance"]["properties"]
    assert provenance["spec_id"]["anyOf"][0]["pattern"] == REGISTERED_ID_PATTERN
    raw = ParserResult.model_json_schema()
    assert CLAIM_ID_PATTERN in json.dumps(raw)


def test_speculative_status_can_be_operational_or_not() -> None:
    operational = _defined_claim()
    non_operational = _defined_claim(is_operational=False, epistemic_status="speculative")

    assert operational.is_operational is True
    assert operational.epistemic_status.value == "speculative"
    assert non_operational.is_operational is False
    assert non_operational.epistemic_status.value == "speculative"


def test_operationality_follows_definitions_not_epistemic_status() -> None:
    for status in ("speculative", "hypothesis", "unknown"):
        claim = _defined_claim(epistemic_status=status)
        assert claim.is_operational is True

    with pytest.raises(ValidationError):
        _defined_claim(
            variables=[{"name": "length", "defined": False}],
            epistemic_status="hypothesis",
        )
    with pytest.raises(ValidationError):
        _defined_claim(
            missing_definitions=[
                {"statement": "No instrument was named for the period.", "critical": True}
            ]
        )
    optional = _defined_claim(
        missing_definitions=[
            {"statement": "The text does not name the bob material.", "critical": False}
        ]
    )
    assert optional.is_operational is True


def test_parser_schema_rejects_duplicate_claim_ids() -> None:
    from app.schemas.claim import EpistemicStatus
    from app.schemas.parser import MissingDefinition

    claim = ParsedClaim(
        claim_id="c1",
        statement="A named effect occurs.",
        claim_type=ClaimType.EMPIRICAL,
        is_operational=False,
        missing_definitions=[
            MissingDefinition(statement="no quantity was stated", critical=True)
        ],
        provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
        epistemic_status=EpistemicStatus.SPECULATIVE,
        confidence=ExtractionConfidence.LOW,
    )

    with pytest.raises(ValidationError):
        ParserResult(claims=[claim, claim.model_copy(update={"statement": "Another wording."})])


def test_structured_output_schema_has_no_local_refs() -> None:
    schema = strict_json_schema(ParserResult)

    assert "$ref" not in json.dumps(schema)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False


def test_parser_and_critic_schemas_fit_strict_structured_output() -> None:
    for model in (ParserResult, CritiqueReport):
        schema = strict_json_schema(model)

        assert strict_subset_issues(schema) == []
        assert schema["type"] == "object"
