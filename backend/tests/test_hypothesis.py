"""Validation tests for HypothesisInput."""

import pytest
from pydantic import ValidationError

from app.schemas.hypothesis import HypothesisInput


def test_accepts_a_statement_and_strips_surrounding_space() -> None:
    hypothesis = HypothesisInput(
        statement="  Increased salinity lowers germination.  ",
        domain=" plant physiology ",
        context=" Greenhouse trial proposed by the user. ",
        assumptions=["  Temperature is held constant.  "],
    )

    assert hypothesis.statement == "Increased salinity lowers germination."
    assert hypothesis.domain == "plant physiology"
    assert hypothesis.context == "Greenhouse trial proposed by the user."
    assert hypothesis.assumptions == ["Temperature is held constant."]


def test_statement_may_stand_alone() -> None:
    hypothesis = HypothesisInput(statement="The oscillator period depends on amplitude.")

    assert hypothesis.domain is None
    assert hypothesis.context is None
    assert hypothesis.assumptions == []


def test_rejects_blank_statement() -> None:
    with pytest.raises(ValidationError):
        HypothesisInput(statement="   ")


def test_rejects_blank_assumption() -> None:
    with pytest.raises(ValidationError):
        HypothesisInput(
            statement="Damping decreases with temperature.",
            assumptions=["kept the mass fixed", "   "],
        )


def test_rejects_a_verdict_smuggled_onto_the_input() -> None:
    with pytest.raises(ValidationError):
        HypothesisInput.model_validate(
            {
                "statement": "Increasing salinity lowers germination.",
                "verdict": "NOT_YET_FALSIFIABLE",
            }
        )
