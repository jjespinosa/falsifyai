"""Variable identity is separate from a missing number. These tests do not call the network."""

import pytest
from pydantic import ValidationError

from app.config import load_settings
from app.prompts.parser import PARSER_SYSTEM_PROMPT
from app.schemas.claim import ClaimProvenance, EpistemicStatus, EvidenceOrigin
from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import (
    ClaimType,
    ClaimVariable,
    ExtractionConfidence,
    MissingDefinition,
    ParsedClaim,
    ParserResult,
)
from app.services.m2_fixtures import CASE_MASS
from app.services.modes import ExecutionMode
from app.services.parser import parse_hypothesis

_STATEMENT = (
    "At fixed pendulum length and within the small-angle regime, "
    "increasing the bob mass changes the oscillation period."
)


def _claim(**updates: object) -> ParsedClaim:
    payload = {
        "claim_id": "c1",
        "statement": _STATEMENT,
        "claim_type": ClaimType.CAUSAL,
        "variables": [
            ClaimVariable(name="bob mass", defined=True),
            ClaimVariable(name="oscillation period", defined=True),
            ClaimVariable(name="pendulum length", defined=True),
        ],
        "is_operational": True,
        "missing_definitions": [
            MissingDefinition(statement="The exact pendulum length is not stated.", critical=False),
            MissingDefinition(
                statement="A numeric small-angle threshold is not stated.",
                critical=False,
            ),
        ],
        "provenance": ClaimProvenance(origin=EvidenceOrigin.ASSUMED, observable="oscillation period"),
        "epistemic_status": EpistemicStatus.HYPOTHESIS,
        "confidence": ExtractionConfidence.MEDIUM,
    }
    payload.update(updates)
    return ParsedClaim(**payload)


def test_named_quantities_stay_defined_when_numbers_are_missing() -> None:
    claim = _claim(
        variables=[
            ClaimVariable(name="bob mass", defined=True),
            ClaimVariable(name="oscillation period", defined=True),
            ClaimVariable(name="pendulum length", defined=True),
            ClaimVariable(name="angular amplitude", defined=True),
        ]
    )
    defined = {item.name: item.defined for item in claim.variables}

    assert defined["bob mass"] is True
    assert defined["oscillation period"] is True
    assert defined["pendulum length"] is True
    assert defined["angular amplitude"] is True
    assert claim.variables[2].unit is None
    assert claim.is_operational is True
    assert all(item.critical is False for item in claim.missing_definitions)


def test_stub_pendulum_uses_the_same_identity_rule() -> None:
    result = parse_hypothesis(
        HypothesisInput(statement=CASE_MASS),
        mode=ExecutionMode.STUB,
        settings=load_settings({}),
    )
    defined = {item.name: item.defined for item in result.claims[0].variables}

    assert defined["bob mass"] is True
    assert defined["oscillation period"] is True
    assert defined["pendulum length"] is True
    assert result.claims[0].is_operational is True
    assert any(item.critical is False for item in result.claims[0].missing_definitions)


def test_undefined_mechanism_quantity_can_stay_undefined() -> None:
    variable = ClaimVariable(
        name="unknown biofield parameter with no operational meaning",
        defined=False,
    )
    claim = _claim(
        statement="An unknown biofield parameter with no operational meaning changes the period.",
        variables=[variable],
        is_operational=False,
        missing_definitions=[
            MissingDefinition(statement="The mechanism has no operational meaning.", critical=True)
        ],
    )

    assert variable.defined is False
    assert claim.is_operational is False


def test_operational_claim_still_rejects_a_genuinely_undefined_variable() -> None:
    with pytest.raises(ValidationError, match="undefined variable"):
        _claim(
            variables=[
                ClaimVariable(
                    name="unknown biofield parameter with no operational meaning",
                    defined=False,
                )
            ]
        )


def test_saved_invalid_live_payload_still_fails_without_normalization() -> None:
    payload = {
        "assumptions": [],
        "claims": [
            {
                "assumptions": [],
                "claim_id": "c1",
                "claim_type": "causal",
                "confidence": "high",
                "epistemic_status": "hypothesis",
                "is_operational": True,
                "missing_definitions": [
                    {
                        "critical": False,
                        "statement": "Threshold defining 'small-angle regime' (e.g., maximum angular amplitude) is not specified.",
                    }
                ],
                "provenance": {"origin": "assumed"},
                "statement": _STATEMENT,
                "variables": [
                    {"defined": False, "name": "bob mass"},
                    {"defined": False, "name": "oscillation period"},
                    {"defined": False, "name": "pendulum length"},
                ],
            }
        ],
        "parser_notes": [],
        "undefined_terms": [],
    }

    with pytest.raises(ValidationError, match="undefined variable"):
        ParserResult.model_validate(payload)
    assert payload["claims"][0]["variables"][0]["defined"] is False
    assert payload["claims"][0]["is_operational"] is True


def test_parser_prompt_separates_identity_from_quantitative_specification() -> None:
    assert "defined=true means the physical or mathematical quantity is sufficiently identified" in PARSER_SYSTEM_PROMPT
    assert "defined=true does not require that quantitative specification." in PARSER_SYSTEM_PROMPT
    assert "Do not encode missing numerical information by setting defined=false." in PARSER_SYSTEM_PROMPT
    assert "claim_id must be lowercase" in PARSER_SYSTEM_PROMPT
    assert "assumption ids must be lowercase" in PARSER_SYSTEM_PROMPT
    assert "Do not invent evidence or sources." in PARSER_SYSTEM_PROMPT
    assert "Do not add a numeric value or a citation that the user did not write." in PARSER_SYSTEM_PROMPT
    assert "epistemic status" in PARSER_SYSTEM_PROMPT.lower()
    assert "If any variable has defined set to false, set is_operational to false." in PARSER_SYSTEM_PROMPT
