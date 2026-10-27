"""Sanitized checkpoints for one M5 run and a manual resume.

Nothing in this module calls the network or reads environment variables.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.diagnostics.parser_response import redact_json_text
from app.schemas.critic import CritiqueReport
from app.schemas.experiment import ExperimentPlanResult
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.schemas.run import RunRequest
from app.schemas.simulation import SimulationPlanResult, SimulationResult
from app.schemas.verdict import FalsificationVerdict
from app.services.modes import ExecutionMode

STAGE_ORDER = (
    "hypothesis",
    "parser",
    "critic",
    "null_model",
    "observable",
    "simulation_plan",
    "simulation",
    "experiment",
    "judge",
)
RESUME_FROM = (
    "parser",
    "critic",
    "null_model",
    "observable",
    "simulation_plan",
    "experiment",
)
_BEFORE = {
    "parser": ("hypothesis",),
    "critic": ("hypothesis", "parser"),
    "null_model": ("hypothesis", "parser", "critic"),
    "observable": ("hypothesis", "parser", "critic", "null_model"),
    "simulation_plan": ("hypothesis", "parser", "critic", "null_model", "observable"),
    "experiment": (
        "hypothesis",
        "parser",
        "critic",
        "null_model",
        "observable",
        "simulation_plan",
    ),
}
_MODELS: dict[str, type[BaseModel]] = {
    "hypothesis": HypothesisInput,
    "parser": ParserResult,
    "critic": CritiqueReport,
    "null_model": NullModelResult,
    "observable": ObservableDesignResult,
    "simulation_plan": SimulationPlanResult,
    "simulation": SimulationResult,
    "experiment": ExperimentPlanResult,
    "judge": FalsificationVerdict,
}
_USAGE = (
    "usage: python scripts/live_m5_resume.py --from "
    "parser|critic|null_model|observable|simulation_plan|experiment"
)


class ResumeRefused(ValueError):
    """The checkpoint cannot support the requested stage."""


@dataclass(frozen=True)
class ResumeSelection:
    """Validated objects already accepted before the stage that will run."""

    start: str
    hypothesis: HypothesisInput
    parser: ParserResult | None
    critique: CritiqueReport | None
    null_model: NullModelResult | None
    observables: ObservableDesignResult | None
    simulation_plan: SimulationPlanResult | None
    simulation: SimulationResult | None
    simulation_skipped: bool
    experiment: ExperimentPlanResult | None


def write_run_checkpoint(
    path: Path,
    stages: dict[str, BaseModel],
    *,
    secret: str,
    simulation_skipped: bool | None = None,
) -> str:
    """Write the validated stages so far. Return the last stage name."""

    present = [name for name in STAGE_ORDER if name in stages]
    if not present:
        raise ResumeRefused("a checkpoint needs at least one validated stage")
    unknown = [name for name in stages if name not in _MODELS]
    if unknown:
        raise ResumeRefused("checkpoint stage is not part of the run")
    document = {
        "last_valid_stage": present[-1],
        "simulation_skipped": simulation_skipped,
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


def parse_resume_args(argv: list[str]) -> tuple[str, Path | None]:
    """Read --from and an optional --checkpoint. This does not open the file."""

    if len(argv) not in (2, 4) or argv[0] != "--from" or argv[1] not in RESUME_FROM:
        raise ResumeRefused(_USAGE)
    if len(argv) == 2:
        return argv[1], None
    if argv[2] != "--checkpoint":
        raise ResumeRefused(_USAGE)
    return argv[1], Path(argv[3])


def load_resume(path: Path, stage: str) -> ResumeSelection:
    """Load and revalidate a checkpoint before any model call."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResumeRefused("checkpoint is not JSON") from exc
    except OSError as exc:
        raise ResumeRefused("checkpoint could not be read") from exc
    return select_resume(document, stage)


def select_resume(document: object, stage: str) -> ResumeSelection:
    """Validate every object the requested stage consumes."""

    if stage not in RESUME_FROM:
        raise ResumeRefused("resume stage is not available")
    if not isinstance(document, dict):
        raise ResumeRefused("checkpoint must be an object")
    stages = document.get("stages")
    if not isinstance(stages, dict):
        raise ResumeRefused("checkpoint has no stages")
    missing = [name for name in _BEFORE[stage] if name not in stages]
    if missing:
        raise ResumeRefused("checkpoint is missing a validated upstream stage: " + ",".join(missing))
    validated = {name: _validate_stage(name, stages[name]) for name in _BEFORE[stage]}
    simulation: SimulationResult | None = None
    simulation_skipped = False
    if "simulation" in stages:
        simulation = _validate_stage("simulation", stages["simulation"])
    elif stage == "experiment":
        if document.get("simulation_skipped") is not True:
            raise ResumeRefused("experiment resume needs a validated simulation or an explicit skip")
        simulation_skipped = True
    experiment: ExperimentPlanResult | None = None
    if "experiment" in stages:
        experiment = _validate_stage("experiment", stages["experiment"])
    return ResumeSelection(
        start=stage,
        hypothesis=validated["hypothesis"],  # type: ignore[arg-type]
        parser=validated.get("parser"),  # type: ignore[arg-type]
        critique=validated.get("critic"),  # type: ignore[arg-type]
        null_model=validated.get("null_model"),  # type: ignore[arg-type]
        observables=validated.get("observable"),  # type: ignore[arg-type]
        simulation_plan=validated.get("simulation_plan"),  # type: ignore[arg-type]
        simulation=simulation,
        simulation_skipped=simulation_skipped,
        experiment=experiment,
    )


def build_resume_request(selection: ResumeSelection) -> RunRequest:
    """The resumed run stays live and on the economy profile."""

    return RunRequest(
        hypothesis=selection.hypothesis,
        mode=ExecutionMode.LIVE,
        reasoning_profile="economy",
    )


def _validate_stage(name: str, payload: object) -> BaseModel:
    model = _MODELS[name]
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ResumeRefused(f"{name} checkpoint failed validation: {exc.error_count()} errors") from exc
