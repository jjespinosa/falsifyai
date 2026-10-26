"""The hypothesis a user wants FalsifyAI to attack.

A hypothesis input is not evidence and not a verdict.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_STATEMENT = 4_000
_MAX_CONTEXT = 8_000
_MAX_ITEM = 500
_MAX_ASSUMPTIONS = 20


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class HypothesisInput(BaseModel):
    """Raw hypothesis submitted for later adversarial examination."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=_MAX_STATEMENT)
    domain: str | None = Field(default=None, max_length=200)
    context: str | None = Field(default=None, max_length=_MAX_CONTEXT)
    assumptions: list[str] = Field(default_factory=list, max_length=_MAX_ASSUMPTIONS)

    @field_validator("statement", "domain", "context", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("domain", "context")
    @classmethod
    def _reject_blank_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "":
            raise ValueError("must not be blank")
        return value

    @field_validator("assumptions", mode="before")
    @classmethod
    def _strip_assumptions(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        stripped: list[object] = []
        for item in value:
            stripped.append(item.strip() if isinstance(item, str) else item)
        return stripped

    @field_validator("assumptions")
    @classmethod
    def _substantive_assumptions(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "":
                raise ValueError("assumptions must not contain blank items")
            if len(item) > _MAX_ITEM:
                raise ValueError("an assumption exceeds 500 characters")
        return value
