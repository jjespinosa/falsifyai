"""Declarative simulation plan and numerical result. Neither is a verdict."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.critic import CritiqueReport
from app.schemas.hypothesis import HypothesisInput
from app.schemas.identifiers import OBSERVABLE_ID_PATTERN, SIMULATION_ID_PATTERN
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.simulation.limits import (
    MAX_ABS_COORDINATE,
    MAX_GRID_POINTS,
    MAX_SWEEP_POINTS,
    require_evaluation_budget,
)
from app.simulation.registry import FAMILIES, PARAMETER_NAMES, active_parameters

FamilyName = Literal["constant", "linear", "quadratic", "exponential_decay"]
TemplateName = Literal["static_curve", "parameter_sweep"]
OutputName = Literal["h0", "h1", "delta"]
PlanStatus = Literal["ready", "blocked"]
SweepTarget = Literal["h0", "h1"]
ParameterName = Literal[
    "value",
    "slope",
    "intercept",
    "quadratic",
    "amplitude",
    "rate",
    "offset",
]


def _finite_number(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if not math.isfinite(float(value)):
        raise ValueError("value must be finite")
    return value


def _bounded_coordinate(value: float) -> float:
    if abs(value) > MAX_ABS_COORDINATE:
        raise ValueError("coordinate range exceeds the configured maximum")
    return value


class FamilyParameters(BaseModel):
    """Closed parameter object. Unused fields stay null."""

    model_config = ConfigDict(extra="forbid")

    value: float | None
    slope: float | None
    intercept: float | None
    quadratic: float | None
    amplitude: float | None
    rate: float | None
    offset: float | None

    @field_validator(*PARAMETER_NAMES)
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not math.isfinite(value):
            raise ValueError("parameter must be finite")
        return float(value)


class ModelCurve(BaseModel):
    """One side of a comparison, selected from the registered families."""

    model_config = ConfigDict(extra="forbid")

    family: FamilyName
    parameters: FamilyParameters

    @model_validator(mode="after")
    def _parameters_match_family(self) -> ModelCurve:
        active_parameters(self.family, self.parameters.model_dump())
        return self


class IndependentVariable(BaseModel):
    """Finite grid for the observable's independent variable."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    units: str = Field(min_length=1, max_length=64)
    min: float
    max: float
    points: int = Field(ge=1, le=MAX_GRID_POINTS)

    @field_validator("min", "max", mode="before")
    @classmethod
    def _finite_bounds(cls, value: object) -> object:
        return _finite_number(value)

    @model_validator(mode="after")
    def _grid_is_ordered(self) -> IndependentVariable:
        _bounded_coordinate(self.min)
        _bounded_coordinate(self.max)
        if self.max < self.min:
            raise ValueError("invalid grid")
        if self.points == 1 and self.max != self.min:
            raise ValueError("invalid grid")
        return self


class ParameterSweep(BaseModel):
    """One registered parameter varied over a finite range."""

    model_config = ConfigDict(extra="forbid")

    target: SweepTarget
    parameter: ParameterName
    min: float
    max: float
    points: int = Field(ge=1, le=MAX_SWEEP_POINTS)

    @field_validator("min", "max", mode="before")
    @classmethod
    def _finite_bounds(cls, value: object) -> object:
        return _finite_number(value)

    @model_validator(mode="after")
    def _sweep_is_ordered(self) -> ParameterSweep:
        _bounded_coordinate(self.min)
        _bounded_coordinate(self.max)
        if self.max < self.min:
            raise ValueError("invalid sweep")
        if self.points == 1 and self.max != self.min:
            raise ValueError("invalid sweep")
        return self


class SimulationSpec(BaseModel):
    """Declarative comparison. It contains no executable source."""

    model_config = ConfigDict(extra="forbid")

    simulation_id: str = Field(pattern=SIMULATION_ID_PATTERN)
    observable_id: str = Field(pattern=OBSERVABLE_ID_PATTERN)
    template: TemplateName
    independent_variable: IndependentVariable
    h0: ModelCurve
    h1: ModelCurve
    outputs: list[OutputName] = Field(min_length=3, max_length=3)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    seed: int = Field(ge=0, le=2_147_483_647)
    sweep: ParameterSweep | None

    @field_validator("assumptions")
    @classmethod
    def _assumptions_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item.strip() == "":
                raise ValueError("assumptions must not contain blank items")
        return value

    @model_validator(mode="after")
    def _spec_is_executable(self) -> SimulationSpec:
        if set(self.outputs) != {"h0", "h1", "delta"}:
            raise ValueError("outputs must be h0, h1, and delta")
        if self.template == "static_curve":
            if self.sweep is not None:
                raise ValueError("static_curve does not take a parameter sweep")
            require_evaluation_budget(self.independent_variable.points, 1)
        else:
            if self.sweep is None:
                raise ValueError("parameter_sweep requires one sweep axis")
            if self.independent_variable.points != 1:
                raise ValueError("parameter_sweep evaluates one fixed observable coordinate")
            require_evaluation_budget(1, self.sweep.points)
            target_curve = self.h0 if self.sweep.target == "h0" else self.h1
            if self.sweep.parameter not in FAMILIES[target_curve.family]:
                raise ValueError("sweep parameter is not part of the selected family")
        return self


class SimulationPlanResult(BaseModel):
    """Whether a numerical comparison is defined. Blocked is a valid result."""

    model_config = ConfigDict(extra="forbid")

    status: PlanStatus
    observable_id: str | None = Field(default=None, pattern=OBSERVABLE_ID_PATTERN)
    spec: SimulationSpec | None
    blocking_missing_definitions: list[str] = Field(max_length=12)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    summary: str = Field(min_length=1, max_length=2_000)

    @field_validator("blocking_missing_definitions", "assumptions")
    @classmethod
    def _items_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item.strip() == "":
                raise ValueError("items must not be blank")
        return value

    @model_validator(mode="after")
    def _status_matches_spec(self) -> SimulationPlanResult:
        if self.status == "blocked":
            if self.spec is not None:
                raise ValueError("a blocked plan must not include a spec")
            if not self.blocking_missing_definitions:
                raise ValueError("a blocked plan must name a missing definition")
            return self
        if self.spec is None:
            raise ValueError("a ready plan must include a spec")
        if self.blocking_missing_definitions:
            raise ValueError("a ready plan must not list blocking missing definitions")
        if self.observable_id != self.spec.observable_id:
            raise ValueError("spec observable_id must match the selected observable")
        return self


class SimulationResultMetadata(BaseModel):
    """How a stored curve was produced. It is not a statistical summary."""

    model_config = ConfigDict(extra="forbid")

    template: TemplateName
    points: int = Field(ge=1, le=MAX_GRID_POINTS)
    seed: int = Field(ge=0, le=2_147_483_647)


class SimulationResult(BaseModel):
    """Model-prediction curves. delta is h1 minus h0, not evidence."""

    model_config = ConfigDict(extra="forbid")

    simulation_id: str = Field(pattern=SIMULATION_ID_PATTERN)
    observable_id: str = Field(pattern=OBSERVABLE_ID_PATTERN)
    x: list[float] = Field(min_length=1, max_length=MAX_GRID_POINTS)
    h0: list[float] = Field(min_length=1, max_length=MAX_GRID_POINTS)
    h1: list[float] = Field(min_length=1, max_length=MAX_GRID_POINTS)
    delta: list[float] = Field(min_length=1, max_length=MAX_GRID_POINTS)
    metadata: SimulationResultMetadata

    @field_validator("x", "h0", "h1", "delta")
    @classmethod
    def _finite_series(cls, value: list[float]) -> list[float]:
        for item in value:
            if isinstance(item, bool) or not math.isfinite(item):
                raise ValueError("numerical output must be finite")
        return value

    @model_validator(mode="after")
    def _series_match(self) -> SimulationResult:
        length = len(self.x)
        if len(self.h0) != length or len(self.h1) != length or len(self.delta) != length:
            raise ValueError("result arrays must have equal length")
        if self.metadata.points != length:
            raise ValueError("metadata points must match the result length")
        return self


class SimulationPlanInput(BaseModel):
    """Request body for the simulation planner."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisInput
    parser_result: ParserResult
    critique_report: CritiqueReport
    null_model_result: NullModelResult
    observable_design: ObservableDesignResult
