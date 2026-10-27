"""One synchronous falsification run. It adds no scientific stage."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.critic import CritiqueReport
from app.schemas.experiment import ExperimentPlanResult
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.schemas.simulation import SimulationPlanResult, SimulationResult
from app.schemas.verdict import FalsificationVerdict
from app.services.modes import ExecutionMode

RUN_ID_PATTERN = r"^run_[a-z0-9]{8,32}$"
StageName = Literal[
    "parser",
    "critic",
    "null_model",
    "observable",
    "simulation_plan",
    "simulation",
    "experiment",
    "judge",
]
StageStatus = Literal["pending", "running", "success", "blocked", "failed", "skipped"]
RunOutcome = Literal["completed", "scientifically_blocked", "failed"]
ReasoningProfileName = Literal["economy", "balanced"]


class RunRequest(BaseModel):
    """One hypothesis and the explicit execution choice."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisInput
    mode: ExecutionMode = ExecutionMode.STUB
    reasoning_profile: ReasoningProfileName = "economy"


class StageRecord(BaseModel):
    """Compact progress for one existing pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    name: StageName
    status: StageStatus
    detail: str = ""
    elapsed_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


class RunSummary(BaseModel):
    """Deterministic reading of validated stage outputs. No extra model call."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    null_model: str
    observable: str | None
    simulation_status: str
    experiment_status: str
    verdict: str
    primary_reason: str
    required_next_definition: str | None


class UsageSummary(BaseModel):
    """Token totals for the live model stages in this run. Stub totals stay zero."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    model_calls: int = 0
    elapsed_ms: int = 0


class RunResult(BaseModel):
    """The full validated state a judge can read without a raw-JSON-only screen."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(pattern=RUN_ID_PATTERN)
    status: RunOutcome
    hypothesis_text: str
    stages: list[StageRecord]
    parser: ParserResult | None = None
    critique: CritiqueReport | None = None
    null_model: NullModelResult | None = None
    observable_design: ObservableDesignResult | None = None
    simulation_plan: SimulationPlanResult | None = None
    simulation_result: SimulationResult | None = None
    experiment: ExperimentPlanResult | None = None
    verdict: FalsificationVerdict | None = None
    summary: RunSummary | None = None
    usage: UsageSummary
    error: str | None = None


class ExampleCard(BaseModel):
    """One selectable demo hypothesis."""

    model_config = ConfigDict(extra="forbid")

    example_id: Literal["pendulum", "vague_field", "synthetic"]
    title: str
    purpose: str
    statement: str
    notice: str | None = None


class ExampleList(BaseModel):
    """The three M5 demos."""

    model_config = ConfigDict(extra="forbid")

    examples: list[ExampleCard]
