"""Validation tests for ScientificClaim."""

import pytest
from pydantic import ValidationError

from app.schemas.claim import EvidenceOrigin, ScientificClaim


def test_measured_claim_names_an_observable_and_a_unit() -> None:
    claim = ScientificClaim(
        statement="The measured period on this run was 2.04 seconds.",
        origin=EvidenceOrigin.MEASURED,
        observable=" oscillation period ",
        value=2.04,
        unit=" s ",
    )

    assert claim.origin is EvidenceOrigin.MEASURED
    assert claim.observable == "oscillation period"
    assert claim.value == 2.04
    assert claim.unit == "s"


def test_literature_claim_requires_a_source() -> None:
    claim = ScientificClaim(
        statement="A published estimate of the period is 2 seconds.",
        origin="literature-derived",
        source_ref="doi:10.0000/example",
        value=2,
        unit="s",
    )

    assert claim.origin is EvidenceOrigin.LITERATURE_DERIVED
    assert claim.value == 2.0


def test_assumed_claim_needs_no_measurement() -> None:
    claim = ScientificClaim(statement="Damping is negligible.", origin="assumed")

    assert claim.origin is EvidenceOrigin.ASSUMED
    assert claim.observable is None
    assert claim.value is None


def test_simulated_claim_names_a_spec_and_a_routine() -> None:
    claim = ScientificClaim(
        statement="The registered routine produced this period.",
        origin="simulated",
        observable="oscillation period",
        spec_id="example_spec",
        routine_id="example_routine",
        value=2.1,
        unit="s",
    )

    assert claim.origin is EvidenceOrigin.SIMULATED
    assert claim.spec_id == "example_spec"
    assert claim.routine_id == "example_routine"


def test_measured_claim_without_observable_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScientificClaim(statement="The period was 2 seconds.", origin="measured", value=2, unit="s")


def test_numeric_value_without_unit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScientificClaim(
            statement="The period was 2 seconds.",
            origin="measured",
            observable="oscillation period",
            value=2,
        )


def test_literature_claim_without_source_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScientificClaim(statement="Published work agrees.", origin="literature-derived")


def test_simulated_claim_without_registered_ids_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScientificClaim(statement="A simulation said so.", origin="simulated")


def test_rejects_non_finite_values() -> None:
    with pytest.raises(ValidationError):
        ScientificClaim(
            statement="The period was not finite.",
            origin="measured",
            observable="oscillation period",
            value=float("nan"),
            unit="s",
        )


def test_rejects_unknown_origin_and_executable_payload() -> None:
    with pytest.raises(ValidationError):
        ScientificClaim.model_validate(
            {"statement": "Unsupported.", "origin": "guessed"}
        )
    with pytest.raises(ValidationError):
        ScientificClaim.model_validate(
            {
                "statement": "Do not run this.",
                "origin": "assumed",
                "code": "print(1)",
            }
        )
