"""Response contract for the process health check."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["falsifyai"]
    milestone: Literal["M1"]
