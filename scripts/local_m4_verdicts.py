"""Local check of the four falsification statuses.

Run it explicitly:

    python scripts/local_m4_verdicts.py

This script does not read the API key and does not call the network.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Print the stub experiment status and verdict for each control case."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.config import load_settings
    from app.services.experiment import design_experiment
    from app.services.judge import judge_hypothesis
    from app.services.m4_fixtures import (
        identical_context,
        low_sensitivity_context,
        pendulum_context,
        quantitative_context,
    )
    from app.services.modes import ExecutionMode

    settings = load_settings({})
    cases = (
        ("NOT_YET_FALSIFIABLE", pendulum_context()),
        ("TESTABLE", quantitative_context()),
        ("BELOW_SENSITIVITY", low_sensitivity_context()),
        ("NON_DISCRIMINATING", identical_context()),
    )
    for expected, ctx in cases:
        experiment = design_experiment(
            ctx.hypothesis,
            ctx.parser_result,
            ctx.critique,
            ctx.null_model,
            ctx.observables,
            ctx.simulation_plan,
            None,
            mode=ExecutionMode.STUB,
            settings=settings,
        )
        verdict = judge_hypothesis(
            ctx.hypothesis,
            ctx.parser_result,
            ctx.critique,
            ctx.null_model,
            ctx.observables,
            ctx.simulation_plan,
            None,
            experiment,
            ctx.capability,
            mode=ExecutionMode.STUB,
            settings=settings,
        )
        resolution = "none"
        if experiment.experiment is not None:
            resolution = experiment.experiment.required_resolution.status
        print(f"case: {expected}")
        print(f"experiment_status: {experiment.status}")
        print(f"resolution_status: {resolution}")
        print(f"judge_status: {verdict.status}")
        print(f"delta_over_sigma: {verdict.delta_over_sigma}")
        print(f"match: {str(verdict.status == expected).lower()}")
    print("model_api_calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
