"""A competing explanation H0. It is not a verdict and not a measurement."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.hypothesis import HypothesisInput
from app.schemas.identifiers import NULL_MODEL_ID_PATTERN, ClaimId
from app.schemas.critic import CritiqueReport
from app.schemas.parser import ParserResult


class KnowledgeBasis(str, Enum):
    """Where a statement in H0 came from."""

    USER_SUPPLIED = "user_supplied"
    STANDARD_KNOWLEDGE = "standard_knowledge"
    COMPARISON_ASSUMPTION = "comparison_assumption"


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class SourcedStatement(BaseModel):
    """One equation or assumption, labeled by its basis."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=1_000)
    basis: KnowledgeBasis

    @field_validator("statement", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _strip_text(value)


class NullModel(BaseModel):
    """The strongest reasonable conventional account of the same claim."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(pattern=NULL_MODEL_ID_PATTERN)
    description: str = Field(min_length=1, max_length=2_000)
    target_claim_ids: list[ClaimId] = Field(min_length=1)
    assumptions: list[SourcedStatement] = Field(default_factory=list, max_length=20)
    equations: list[SourcedStatement] = Field(default_factory=list, max_length=10)
    free_parameters: list[str] = Field(default_factory=list, max_length=20)
    known_confounders: list[str] = Field(default_factory=list, max_length=20)
    can_mimic_claim: bool = Field(
        description=(
            "Whether the full null explanation, including declared nuisance parameters "
            "and known confounders, can reproduce an apparent form of the claim."
        )
    )
    mimicry_reason: str = Field(min_length=1, max_length=1_000)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    basis: KnowledgeBasis
    blocking_missing_definitions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("description", "mimicry_reason", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator(
        "free_parameters",
        "known_confounders",
        "limitations",
        "blocking_missing_definitions",
        mode="before",
    )
    @classmethod
    def _strip_items(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [item.strip() if isinstance(item, str) else item for item in value]

    @field_validator(
        "free_parameters",
        "known_confounders",
        "limitations",
        "blocking_missing_definitions",
    )
    @classmethod
    def _items_not_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("items must not be blank")
        return value


class NullModelResult(BaseModel):
    """Competing models for the parsed claims. This is not a falsification verdict."""

    model_config = ConfigDict(extra="forbid")

    models: list[NullModel] = Field(default_factory=list, max_length=5)
    summary: str = Field(min_length=1, max_length=2_000)

    @field_validator("summary", mode="before")
    @classmethod
    def _strip_summary(cls, value: object) -> object:
        return _strip_text(value)

    @model_validator(mode="after")
    def _identifiers_unique(self) -> NullModelResult:
        model_ids = [item.model_id for item in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("model_id values must be unique")
        return self


class NullModelInput(BaseModel):
    """Request body for the null-model route."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisInput
    parser_result: ParserResult
    critique_report: CritiqueReport


def require_known_targets(claim_ids: list[str], known: set[str], *, label: str) -> None:
    """Reject references to claims the parser did not extract."""

    unknown = [claim_id for claim_id in claim_ids if claim_id not in known]
    if unknown:
        raise ValueError(f"{label} must refer to parsed claims")
