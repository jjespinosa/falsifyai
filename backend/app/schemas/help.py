"""Response contract for the milestone help document."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HelpEndpoint(BaseModel):
    """One HTTP route this milestone actually serves."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST"]
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class HelpVariable(BaseModel):
    """A configuration name and the rule for its use. Values are never included."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    required_for: str = Field(min_length=1)
    notes: str = Field(min_length=1)


class HelpContract(BaseModel):
    """A validated object that does not yet have its own route."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class HelpLink(BaseModel):
    """Where to read the matching documentation."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["guide", "openapi", "redoc"]
    location: str = Field(min_length=1)


class HelpResponse(BaseModel):
    """Static help for milestone M7. It does not reflect the process environment."""

    model_config = ConfigDict(extra="forbid")

    service: Literal["falsifyai"]
    milestone: Literal["M7"]
    summary: str = Field(min_length=1)
    documentation: list[HelpLink]
    endpoints: list[HelpEndpoint]
    configuration: list[HelpVariable]
    contracts: list[HelpContract]
    not_available: list[str]
