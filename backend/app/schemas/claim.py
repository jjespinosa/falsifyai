"""A scientific claim labeled by how its content was obtained.

Provenance is checked here. This schema does not decide whether a hypothesis survives.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.identifiers import REGISTERED_ID_PATTERN


class EvidenceOrigin(str, Enum):
    """How the content was obtained. This is not its scientific status."""

    MEASURED = "measured"
    LITERATURE_DERIVED = "literature-derived"
    ASSUMED = "assumed"
    SIMULATED = "simulated"


class EpistemicStatus(str, Enum):
    """Scientific standing. This is not provenance and not operationality."""

    ESTABLISHED = "established"
    HYPOTHESIS = "hypothesis"
    SPECULATIVE = "speculative"
    UNKNOWN = "unknown"


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class ScientificClaim(BaseModel):
    """One claim plus the provenance required before anyone treats it as data.

    Numeric values are accepted only as caller-supplied data with a unit.
    Nothing in this schema invents a measurement or runs a simulation.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=4_000)
    origin: EvidenceOrigin
    epistemic_status: EpistemicStatus = EpistemicStatus.UNKNOWN
    observable: str | None = Field(default=None, max_length=200)
    source_ref: str | None = Field(default=None, max_length=300)
    spec_id: str | None = Field(default=None, pattern=REGISTERED_ID_PATTERN)
    routine_id: str | None = Field(default=None, pattern=REGISTERED_ID_PATTERN)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=64)

    @field_validator(
        "statement",
        "observable",
        "source_ref",
        "unit",
        "spec_id",
        "routine_id",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("observable", "source_ref", "unit")
    @classmethod
    def _reject_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "":
            raise ValueError("must not be blank")
        return value

    @field_validator("value", mode="before")
    @classmethod
    def _numeric_value(cls, value: object) -> object:
        if value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)):
            return value
        raise ValueError("value must be a finite number")

    @field_validator("value")
    @classmethod
    def _finite_value(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value):
            raise ValueError("value must be a finite number")
        return value

    @model_validator(mode="after")
    def _check_provenance(self) -> ScientificClaim:
        enforce_provenance(
            origin=self.origin,
            observable=self.observable,
            source_ref=self.source_ref,
            spec_id=self.spec_id,
            routine_id=self.routine_id,
            value=self.value,
            unit=self.unit,
        )
        enforce_epistemic_status(self.origin, self.epistemic_status)
        return self


def enforce_provenance(
    *,
    origin: EvidenceOrigin,
    observable: str | None,
    source_ref: str | None,
    spec_id: str | None,
    routine_id: str | None,
    value: float | None,
    unit: str | None,
) -> None:
    """Apply the same provenance rules to every claim shape."""

    if value is not None and unit is None:
        raise ValueError("a numeric value requires a unit")

    simulation_ids = spec_id is not None or routine_id is not None
    if origin is not EvidenceOrigin.SIMULATED and simulation_ids:
        raise ValueError("only a simulated claim may name spec_id or routine_id")

    if origin is EvidenceOrigin.MEASURED and not observable:
        raise ValueError("a measured claim requires an observable")

    if origin is EvidenceOrigin.LITERATURE_DERIVED and not source_ref:
        raise ValueError("a literature-derived claim requires source_ref")

    if origin is EvidenceOrigin.SIMULATED:
        if spec_id is None or routine_id is None:
            raise ValueError("a simulated claim requires spec_id and routine_id")
        if source_ref is not None:
            raise ValueError("a simulated claim uses spec_id and routine_id, not source_ref")


def enforce_epistemic_status(origin: EvidenceOrigin, status: EpistemicStatus) -> None:
    """Established status requires evidence the caller actually supplied."""

    if status is EpistemicStatus.ESTABLISHED and origin not in {
        EvidenceOrigin.MEASURED,
        EvidenceOrigin.LITERATURE_DERIVED,
    }:
        raise ValueError(
            "established status requires measured or literature-derived provenance"
        )


class ClaimProvenance(BaseModel):
    """Provenance block for a parsed claim. Rules match ScientificClaim."""

    model_config = ConfigDict(extra="forbid")

    origin: EvidenceOrigin
    observable: str | None = Field(default=None, max_length=200)
    source_ref: str | None = Field(default=None, max_length=300)
    spec_id: str | None = Field(default=None, pattern=REGISTERED_ID_PATTERN)
    routine_id: str | None = Field(default=None, pattern=REGISTERED_ID_PATTERN)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=64)

    @field_validator("observable", "source_ref", "unit", "spec_id", "routine_id", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("observable", "source_ref", "unit")
    @classmethod
    def _reject_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "":
            raise ValueError("must not be blank")
        return value

    @field_validator("value", mode="before")
    @classmethod
    def _numeric_value(cls, value: object) -> object:
        if value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)):
            return value
        raise ValueError("value must be a finite number")

    @field_validator("value")
    @classmethod
    def _finite_value(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value):
            raise ValueError("value must be a finite number")
        return value

    @model_validator(mode="after")
    def _check_provenance(self) -> ClaimProvenance:
        enforce_provenance(
            origin=self.origin,
            observable=self.observable,
            source_ref=self.source_ref,
            spec_id=self.spec_id,
            routine_id=self.routine_id,
            value=self.value,
            unit=self.unit,
        )
        return self
