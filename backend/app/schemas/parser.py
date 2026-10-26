"""Parser output. A parsed claim keeps the scientific provenance rules."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.claim import ClaimProvenance, EvidenceOrigin

_CLAIM_ID = re.compile(r"^c[1-9][0-9]{0,3}$")
_ASSUMPTION_ID = re.compile(r"^a[1-9][0-9]{0,3}$")


class ClaimType(str, Enum):
    """What kind of proposition a claim is. This is not a verdict."""

    EMPIRICAL = "empirical"
    CAUSAL = "causal"
    PREDICTIVE = "predictive"
    DEFINITIONAL = "definitional"
    MECHANISTIC = "mechanistic"


class ExtractionConfidence(str, Enum):
    """Confidence that the extraction follows the text, not that the claim is true."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class ClaimVariable(BaseModel):
    """A quantity named by a claim."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=64)
    defined: bool

    @field_validator("name", "unit", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("unit")
    @classmethod
    def _unit_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "":
            raise ValueError("must not be blank")
        return value


class ParsedClaim(BaseModel):
    """One scientific claim extracted from a hypothesis."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    statement: str = Field(min_length=1, max_length=4_000)
    claim_type: ClaimType
    variables: list[ClaimVariable] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    is_operational: bool
    missing_definitions: list[str] = Field(default_factory=list, max_length=20)
    provenance: ClaimProvenance
    confidence: ExtractionConfidence

    @field_validator("claim_id", "statement", mode="before")
    @classmethod
    def _strip_identity(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("claim_id")
    @classmethod
    def _claim_id_shape(cls, value: str) -> str:
        if _CLAIM_ID.fullmatch(value) is None:
            raise ValueError("claim_id must look like c1")
        return value

    @field_validator("assumptions", "missing_definitions", mode="before")
    @classmethod
    def _strip_items(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @field_validator("assumptions", "missing_definitions")
    @classmethod
    def _items_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("items must not be blank")
        return value

    @model_validator(mode="after")
    def _operational_means_defined(self) -> ParsedClaim:
        if not self.is_operational:
            return self
        if self.provenance.origin is EvidenceOrigin.SPECULATIVE:
            raise ValueError("a speculative claim is not operational")
        if self.missing_definitions:
            raise ValueError("an operational claim cannot list missing definitions")
        if any(not variable.defined for variable in self.variables):
            raise ValueError("an operational claim cannot include an undefined variable")
        if not self.variables and self.provenance.observable is None:
            raise ValueError("an operational claim needs a defined quantity")
        return self


class ExtractedAssumption(BaseModel):
    """An assumption noticed in the hypothesis. It is not evidence."""

    model_config = ConfigDict(extra="forbid")

    assumption_id: str
    statement: str = Field(min_length=1, max_length=500)
    claim_ids: list[str] = Field(min_length=1)

    @field_validator("assumption_id", "statement", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("assumption_id")
    @classmethod
    def _assumption_id_shape(cls, value: str) -> str:
        if _ASSUMPTION_ID.fullmatch(value) is None:
            raise ValueError("assumption_id must look like a1")
        return value


class UndefinedTerm(BaseModel):
    """A term that is not tied to a controlled, measured, or defined quantity."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
    claim_ids: list[str] = Field(min_length=1)

    @field_validator("term", "reason", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _strip_text(value)


class ParserResult(BaseModel):
    """The smallest set of claims found in a hypothesis."""

    model_config = ConfigDict(extra="forbid")

    claims: list[ParsedClaim] = Field(min_length=1)
    assumptions: list[ExtractedAssumption] = Field(default_factory=list)
    undefined_terms: list[UndefinedTerm] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _identifiers_resolve(self) -> ParserResult:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique")
        known = set(claim_ids)
        assumption_ids = [item.assumption_id for item in self.assumptions]
        if len(assumption_ids) != len(set(assumption_ids)):
            raise ValueError("assumption_id values must be unique")
        for item in (*self.assumptions, *self.undefined_terms):
            unknown = [claim_id for claim_id in item.claim_ids if claim_id not in known]
            if unknown:
                raise ValueError("claim_ids must refer to extracted claims")
        return self
