"""Whether the current state defines a finite falsifying experiment."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.experiment import ExperimentInput, ExperimentPlanResult
from app.schemas.identifiers import EVIDENCE_REF_PATTERN

VerdictStatus = Literal[
    "TESTABLE",
    "BELOW_SENSITIVITY",
    "NON_DISCRIMINATING",
    "NOT_YET_FALSIFIABLE",
]
CapabilitySource = Literal["user_supplied", "fixture_supplied"]


class ExperimentalCapability(BaseModel):
    """An uncertainty the user or a fixture explicitly supplied."""

    model_config = ConfigDict(extra="forbid")

    observable_id: str = Field(pattern=r"^o[1-9][0-9]*$")
    uncertainty: float = Field(gt=0)
    units: str = Field(min_length=1, max_length=64)
    source: CapabilitySource

    @field_validator("uncertainty")
    @classmethod
    def _finite(cls, value: float) -> float:
        if isinstance(value, bool) or not math.isfinite(value):
            raise ValueError("uncertainty must be finite")
        return float(value)


class FalsificationVerdict(BaseModel):
    """One status. It does not assign a probability that the hypothesis is true."""

    model_config = ConfigDict(extra="forbid")

    status: VerdictStatus
    primary_reason: str = Field(min_length=1, max_length=2_000)
    falsifier: str = Field(min_length=1, max_length=2_000)
    required_next_definition: str | None
    delta_over_sigma: float | None
    limitations: list[str] = Field(max_length=8)
    evidence_refs: list[str] = Field(min_length=1, max_length=12)

    @field_validator("delta_over_sigma", mode="before")
    @classmethod
    def _finite_ratio(cls, value: object) -> object:
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return value
        if not math.isfinite(float(value)):
            raise ValueError("delta_over_sigma must be finite")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def _refs_are_canonical(cls, value: list[str]) -> list[str]:
        import re

        pattern = re.compile(EVIDENCE_REF_PATTERN)
        for item in value:
            if pattern.fullmatch(item) is None:
                raise ValueError("evidence_refs must use canonical ids")
        if len(set(value)) != len(value):
            raise ValueError("evidence_refs must be unique")
        return value

    @field_validator("limitations", mode="before")
    @classmethod
    def _strip_limitations(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @field_validator("limitations")
    @classmethod
    def _limitations_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("limitations must not be blank")
        return value

    @model_validator(mode="after")
    def _status_names_what_is_missing(self) -> FalsificationVerdict:
        if self.status == "NOT_YET_FALSIFIABLE" and not self.required_next_definition:
            raise ValueError("NOT_YET_FALSIFIABLE names the missing definition")
        if self.status == "TESTABLE" and self.required_next_definition is not None:
            raise ValueError("TESTABLE leaves required_next_definition empty")
        return self


class JudgeInput(ExperimentInput):
    """Request body for the falsification judge."""

    experiment_plan: ExperimentPlanResult
    capability: ExperimentalCapability | None
