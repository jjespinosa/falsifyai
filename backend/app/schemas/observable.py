"""A proposed measurement that might separate H1 from H0. It is not a verdict."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.hypothesis import HypothesisInput
from app.schemas.identifiers import OBSERVABLE_ID_PATTERN, ClaimId
from app.schemas.critic import CritiqueReport
from app.schemas.null_model import NullModelResult
from app.schemas.parser import ParserResult


class PredictedDifference(str, Enum):
    """How H1 and H0 differ. This is not an effect size."""

    INCREASE = "increase"
    DECREASE = "decrease"
    NON_MONOTONIC = "non_monotonic"
    ZERO = "zero"
    QUALITATIVE_DIFFERENCE = "qualitative_difference"
    UNKNOWN = "unknown"


_DIFFERENT = {
    PredictedDifference.INCREASE,
    PredictedDifference.DECREASE,
    PredictedDifference.NON_MONOTONIC,
    PredictedDifference.QUALITATIVE_DIFFERENCE,
}


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class ObservableCandidate(BaseModel):
    """One quantity that might separate the claim from its null model."""

    model_config = ConfigDict(extra="forbid")

    observable_id: str = Field(pattern=OBSERVABLE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    symbol: str = Field(min_length=1, max_length=32)
    definition: str = Field(min_length=1, max_length=1_000)
    units: str = Field(min_length=1, max_length=64)
    measurement_method: str = Field(min_length=1, max_length=1_000)
    target_claim_ids: list[ClaimId] = Field(min_length=1)
    h1_prediction: str = Field(min_length=1, max_length=1_000)
    h0_prediction: str = Field(min_length=1, max_length=1_000)
    predicted_difference: PredictedDifference
    required_controls: list[str] = Field(default_factory=list, max_length=20)
    known_confounders: list[str] = Field(default_factory=list, max_length=20)
    blocking_missing_definitions: list[str] = Field(default_factory=list, max_length=20)
    non_blocking_missing_definitions: list[str] = Field(default_factory=list, max_length=20)
    discriminating: bool

    @field_validator(
        "name",
        "symbol",
        "definition",
        "units",
        "measurement_method",
        "h1_prediction",
        "h0_prediction",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator(
        "required_controls",
        "known_confounders",
        "blocking_missing_definitions",
        "non_blocking_missing_definitions",
        mode="before",
    )
    @classmethod
    def _strip_items(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @field_validator(
        "required_controls",
        "known_confounders",
        "blocking_missing_definitions",
        "non_blocking_missing_definitions",
    )
    @classmethod
    def _items_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("items must not be blank")
        return value

    @model_validator(mode="after")
    def _discrimination_is_earned(self) -> ObservableCandidate:
        if not self.discriminating:
            return self
        if self.predicted_difference not in _DIFFERENT:
            raise ValueError("a discriminating observable needs different H1 and H0 predictions")
        if self.blocking_missing_definitions:
            raise ValueError("a discriminating observable cannot list blocking missing definitions")
        if self.known_confounders and not self.required_controls:
            raise ValueError("known confounders need controls before the observable can discriminate")
        return self

    @model_validator(mode="after")
    def _undefined_target_is_not_a_candidate(self) -> ObservableCandidate:
        if self.blocking_missing_definitions:
            raise ValueError("an undefined measurement target is not an observable candidate")
        return self


class ObservableDesignResult(BaseModel):
    """Candidate observables. An empty list is valid when definitions are missing."""

    model_config = ConfigDict(extra="forbid")

    observables: list[ObservableCandidate] = Field(default_factory=list, max_length=8)
    blocking_issues: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2_000)

    @field_validator("summary", mode="before")
    @classmethod
    def _strip_summary(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("blocking_issues", mode="before")
    @classmethod
    def _strip_issues(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @field_validator("blocking_issues")
    @classmethod
    def _issues_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("blocking_issues must not contain blank items")
        return value

    @model_validator(mode="after")
    def _identifiers_unique(self) -> ObservableDesignResult:
        observable_ids = [item.observable_id for item in self.observables]
        if len(observable_ids) != len(set(observable_ids)):
            raise ValueError("observable_id values must be unique")
        return self


class ObservableInput(BaseModel):
    """Request body for the observable route."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisInput
    parser_result: ParserResult
    critique_report: CritiqueReport
    null_model_result: NullModelResult
