"""A scientific claim labeled by how its content was obtained.

Milestone M0 checks provenance. It does not decide whether a hypothesis survives.
"""

from __future__ import annotations

import math
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class EvidenceOrigin(str, Enum):
    """How a claim was obtained. These labels must not be collapsed."""

    MEASURED = "measured"
    LITERATURE_DERIVED = "literature-derived"
    ASSUMED = "assumed"
    SIMULATED = "simulated"


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
    observable: str | None = Field(default=None, max_length=200)
    source_ref: str | None = Field(default=None, max_length=300)
    spec_id: str | None = None
    routine_id: str | None = None
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

    @field_validator("spec_id", "routine_id")
    @classmethod
    def _identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _IDENTIFIER.fullmatch(value) is None:
            raise ValueError("must be a lowercase registered identifier")
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
        if self.value is not None and self.unit is None:
            raise ValueError("a numeric value requires a unit")

        simulation_ids = self.spec_id is not None or self.routine_id is not None
        if self.origin is not EvidenceOrigin.SIMULATED and simulation_ids:
            raise ValueError("only a simulated claim may name spec_id or routine_id")

        if self.origin is EvidenceOrigin.MEASURED and not self.observable:
            raise ValueError("a measured claim requires an observable")

        if self.origin is EvidenceOrigin.LITERATURE_DERIVED and not self.source_ref:
            raise ValueError("a literature-derived claim requires source_ref")

        if self.origin is EvidenceOrigin.SIMULATED:
            if self.spec_id is None or self.routine_id is None:
                raise ValueError("a simulated claim requires spec_id and routine_id")
            if self.source_ref is not None:
                raise ValueError("a simulated claim uses spec_id and routine_id, not source_ref")

        return self
