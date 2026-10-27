"""A controlled comparison. Designing it is not yet a falsification verdict."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.critic import CritiqueReport
from app.schemas.hypothesis import HypothesisInput
from app.schemas.identifiers import EXPERIMENT_ID_PATTERN, OBSERVABLE_ID_PATTERN, ClaimId
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.schemas.simulation import SimulationPlanResult, SimulationResult

CapabilityKind = Literal["required", "assumed", "user_supplied", "unknown"]
DefinitionStatus = Literal["defined", "undefined"]
ExperimentStatus = Literal["ready", "partial", "blocked"]
SAFETY_NOTE = "No autonomous physical execution"


def _finite_or_none(value: object) -> object:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if not math.isfinite(float(value)):
        raise ValueError("value must be finite")
    return value


def _clean_strings(value: object) -> object:
    if not isinstance(value, list):
        return value
    return [item.strip() if isinstance(item, str) else item for item in value]


class ExperimentVariable(BaseModel):
    """One named quantity and whether its capability was actually supplied."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    units: str = Field(min_length=1, max_length=64)
    capability: CapabilityKind


class ParameterScan(BaseModel):
    """A bounded scan. Undefined bounds stay null."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    units: str = Field(min_length=1, max_length=64)
    lower: float | None
    upper: float | None
    status: DefinitionStatus

    @field_validator("lower", "upper", mode="before")
    @classmethod
    def _finite_bounds(cls, value: object) -> object:
        return _finite_or_none(value)

    @model_validator(mode="after")
    def _bounds_match_status(self) -> ParameterScan:
        if self.status == "undefined":
            if self.lower is not None or self.upper is not None:
                raise ValueError("an undefined scan has no numeric bounds")
            return self
        if self.lower is None or self.upper is None or self.upper < self.lower:
            raise ValueError("a defined scan needs ordered finite bounds")
        return self


class RequiredResolution(BaseModel):
    """The separation a decisive measurement would need. Undefined stays null."""

    model_config = ConfigDict(extra="forbid")

    observable_id: str = Field(pattern=OBSERVABLE_ID_PATTERN)
    value: float | None
    units: str = Field(min_length=1, max_length=64)
    basis: str = Field(min_length=1, max_length=1_000)
    status: DefinitionStatus

    @field_validator("value", mode="before")
    @classmethod
    def _finite_value(cls, value: object) -> object:
        return _finite_or_none(value)

    @model_validator(mode="after")
    def _value_matches_status(self) -> RequiredResolution:
        if self.status == "undefined" and self.value is not None:
            raise ValueError("undefined resolution has no numeric value")
        if self.status == "defined" and self.value is None:
            raise ValueError("defined resolution needs a numeric value")
        return self


class ExperimentPlan(BaseModel):
    """The smallest controlled comparison that could address H1 and H0."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=EXPERIMENT_ID_PATTERN)
    objective: str = Field(min_length=1, max_length=1_000)
    target_claim_ids: list[ClaimId] = Field(min_length=1, max_length=8)
    observable_ids: list[Annotated[str, Field(pattern=OBSERVABLE_ID_PATTERN)]] = Field(
        min_length=1, max_length=8
    )
    independent_variables: list[ExperimentVariable] = Field(min_length=1, max_length=8)
    measured_variables: list[ExperimentVariable] = Field(min_length=1, max_length=8)
    controlled_variables: list[ExperimentVariable] = Field(min_length=1, max_length=12)
    control_groups: list[str] = Field(max_length=8)
    parameter_scan: list[ParameterScan] = Field(max_length=8)
    required_resolution: RequiredResolution
    confounders: list[str] = Field(max_length=12)
    procedure_outline: list[str] = Field(min_length=1, max_length=8)
    stop_conditions: list[str] = Field(min_length=1, max_length=8)
    falsifier_candidate: str = Field(min_length=1, max_length=1_000)
    limitations: list[str] = Field(min_length=1, max_length=8)
    safety_notes: list[str] = Field(min_length=1, max_length=4)

    @field_validator(
        "control_groups",
        "confounders",
        "procedure_outline",
        "stop_conditions",
        "limitations",
        "safety_notes",
        mode="before",
    )
    @classmethod
    def _strip_lists(cls, value: object) -> object:
        return _clean_strings(value)

    @field_validator(
        "control_groups",
        "confounders",
        "procedure_outline",
        "stop_conditions",
        "limitations",
        "safety_notes",
    )
    @classmethod
    def _lists_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("items must not be blank")
        return value

    @model_validator(mode="after")
    def _plan_is_traceable(self) -> ExperimentPlan:
        if len(set(self.observable_ids)) != len(self.observable_ids):
            raise ValueError("observable_ids must be unique")
        if self.required_resolution.observable_id not in self.observable_ids:
            raise ValueError("required resolution must name a selected observable")
        if SAFETY_NOTE not in self.safety_notes:
            raise ValueError("safety_notes must include no autonomous physical execution")
        return self


class ExperimentPlanResult(BaseModel):
    """ready, partial, or blocked. Partial is a useful and incomplete design."""

    model_config = ConfigDict(extra="forbid")

    status: ExperimentStatus
    experiment: ExperimentPlan | None
    blocking_missing_definitions: list[str] = Field(max_length=12)
    summary: str = Field(min_length=1, max_length=2_000)

    @field_validator("blocking_missing_definitions", mode="before")
    @classmethod
    def _strip_blockers(cls, value: object) -> object:
        return _clean_strings(value)

    @field_validator("blocking_missing_definitions")
    @classmethod
    def _blockers_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("blocking_missing_definitions must not be blank")
        return value

    @model_validator(mode="after")
    def _status_matches_plan(self) -> ExperimentPlanResult:
        if self.status == "blocked":
            if self.experiment is not None:
                raise ValueError("a blocked experiment has no plan")
            if not self.blocking_missing_definitions:
                raise ValueError("a blocked experiment names a missing definition")
            return self
        if self.experiment is None:
            raise ValueError("a partial or ready result includes an experiment")
        defined = self.experiment.required_resolution.status == "defined"
        if self.status == "ready":
            if not defined or self.blocking_missing_definitions:
                raise ValueError("a ready experiment needs a defined resolution and no blockers")
            return self
        if defined and not self.blocking_missing_definitions:
            raise ValueError("a partial experiment still has an undefined decisive quantity")
        return self


class ExperimentInput(BaseModel):
    """Request body for the experiment designer."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisInput
    parser_result: ParserResult
    critique_report: CritiqueReport
    null_model_result: NullModelResult
    observable_design: ObservableDesignResult
    simulation_plan: SimulationPlanResult
    simulation_result: SimulationResult | None
