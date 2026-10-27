"""Sanitized M4 checkpoints and the parser for a manual one-stage replay.

Nothing in this module calls the network or reads environment variables.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.diagnostics.experiment_response import redact_json_text
from app.schemas.critic import CritiqueReport
from app.schemas.experiment import ExperimentPlanResult
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.schemas.simulation import SimulationPlanResult

STAGE_ORDER = (
    "hypothesis",
    "parser",
    "critic",
    "null",
    "observable",
    "planner",
    "experiment",
)
REPLAY_STAGES = ("experiment", "judge")
_UPSTREAM = ("hypothesis", "parser", "critic", "null", "observable", "planner")
_MODELS: dict[str, type[BaseModel]] = {
    "hypothesis": HypothesisInput,
    "parser": ParserResult,
    "critic": CritiqueReport,
    "null": NullModelResult,
    "observable": ObservableDesignResult,
    "planner": SimulationPlanResult,
    "experiment": ExperimentPlanResult,
}


class ReplayRefused(ValueError):
    """The checkpoint cannot support the requested stage."""


@dataclass(frozen=True)
class ReplaySelection:
    """Validated objects for one manual stage. No secrets and no headers."""

    stage: str
    hypothesis: HypothesisInput
    parser_result: ParserResult
    critique: CritiqueReport
    null_model: NullModelResult
    observables: ObservableDesignResult
    simulation_plan: SimulationPlanResult
    experiment: ExperimentPlanResult | None


def write_checkpoint(path: Path, stages: dict[str, BaseModel], *, secret: str) -> str:
    """Write the validated stages so far. Return the last stage name."""

    present = [name for name in STAGE_ORDER if name in stages]
    if not present:
        raise ReplayRefused("a checkpoint needs at least one validated stage")
    unknown = [name for name in stages if name not in _MODELS]
    if unknown:
        raise ReplayRefused("checkpoint stage is not part of the M4 chain")
    document = {
        "last_valid_stage": present[-1],
        "stages": {name: stages[name].model_dump(mode="json") for name in present},
    }
    text = redact_json_text(json.dumps(document, indent=2, ensure_ascii=False), secret)
    if secret and secret in text:
        raise RuntimeError("refusing to write a checkpoint that still contains the API key")
    if re.search(r"Bearer\s+(?!\[redacted\])\S+", text):
        raise RuntimeError("refusing to write a checkpoint that still contains an authorization token")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return present[-1]


def load_replay(path: Path, stage: str) -> ReplaySelection:
    """Load and validate a checkpoint for experiment-only or judge-only replay."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReplayRefused("checkpoint is not JSON") from exc
    if not isinstance(document, dict):
        raise ReplayRefused("checkpoint must be an object")
    return select_replay(document, stage)


def select_replay(document: object, stage: str) -> ReplaySelection:
    """Validate checkpoint objects. Judge replay requires a valid experiment plan."""

    if stage not in REPLAY_STAGES:
        raise ReplayRefused("replay stage must be experiment or judge")
    if not isinstance(document, dict):
        raise ReplayRefused("checkpoint must be an object")
    stages = document.get("stages")
    if not isinstance(stages, dict):
        raise ReplayRefused("checkpoint has no stages")
    missing = [name for name in _UPSTREAM if name not in stages]
    if missing:
        raise ReplayRefused("checkpoint is missing a validated upstream stage: " + ",".join(missing))
    validated: dict[str, BaseModel] = {}
    for name in _UPSTREAM:
        validated[name] = _validate_stage(name, stages[name])
    experiment: ExperimentPlanResult | None = None
    if "experiment" in stages:
        experiment = _validate_stage("experiment", stages["experiment"])
    if stage == "judge" and experiment is None:
        raise ReplayRefused("judge replay requires a valid ExperimentPlanResult")
    return ReplaySelection(
        stage=stage,
        hypothesis=validated["hypothesis"],  # type: ignore[arg-type]
        parser_result=validated["parser"],  # type: ignore[arg-type]
        critique=validated["critic"],  # type: ignore[arg-type]
        null_model=validated["null"],  # type: ignore[arg-type]
        observables=validated["observable"],  # type: ignore[arg-type]
        simulation_plan=validated["planner"],  # type: ignore[arg-type]
        experiment=experiment,
    )


def _validate_stage(name: str, payload: object) -> BaseModel:
    model = _MODELS[name]
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ReplayRefused(f"{name} checkpoint failed validation: {exc.error_count()} errors") from exc
