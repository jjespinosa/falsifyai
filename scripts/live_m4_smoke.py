"""Manual live canary for milestone M4.

Run it explicitly:

    python scripts/live_m4_smoke.py

It loads the repository-root .env and runs parser, critic, null model,
observable designer, simulation planner, experiment designer, and judge once
each. It does not call the simulator, does not retry, and stops at the first
failure. Importing this module does not call the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

CASE_MASS = (
    "At fixed pendulum length and within the small-angle regime, "
    "increasing the bob mass changes the oscillation period."
)


def main() -> int:
    """Run the implemented chain through the falsification judge."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from live_m1_smoke import REQUIRED_MODEL_ID, load_repo_env, preflight_lines
    from live_m2_smoke import _emit, _failure, _null_summary, _observable_summary, _success

    from app.config import load_settings
    from app.providers.meta import ConfigurationError, ProviderResponseError
    from app.providers.transport import UrllibTransport
    from app.schemas.hypothesis import HypothesisInput
    from app.services.critic import critique_hypothesis
    from app.services.experiment import design_experiment
    from app.services.judge import judge_hypothesis
    from app.services.modes import ExecutionMode
    from app.services.null_model import build_null_model
    from app.services.observable import design_observables
    from app.services.parser import parse_hypothesis
    from app.services.simulation_plan import plan_simulation

    env_detected = load_repo_env(root)
    settings = load_settings()
    secret = settings.model_api_key.get_secret_value()
    lines = preflight_lines(
        env_detected=env_detected,
        key=secret,
        base_url=settings.meta_base_url,
        model_id=settings.meta_model_id,
    )
    lines.append("retries: 0")
    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.append("parser_http: not sent")
        return _emit(lines, secret, ok=False)

    hypothesis = HypothesisInput(statement=CASE_MASS)
    transport = UrllibTransport()
    try:
        parsed = parse_hypothesis(
            hypothesis,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
        )
    except (ConfigurationError, ProviderResponseError) as exc:
        return _stop(lines, secret, "parser", exc, transport, "critic", "null_model", "observable", "planner", "experiment", "judge")
    lines.extend(_success("parser", transport, effort="minimal"))

    try:
        critique = critique_hypothesis(
            hypothesis,
            parsed,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
            reasoning_effort="low",
        )
    except ProviderResponseError as exc:
        return _stop(lines, secret, "critic", exc, transport, "null_model", "observable", "planner", "experiment", "judge")
    lines.extend(_success("critic", transport, effort="low"))

    try:
        null_result = build_null_model(
            hypothesis,
            parsed,
            critique,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
            reasoning_effort="medium",
        )
    except ProviderResponseError as exc:
        return _stop(lines, secret, "null_model", exc, transport, "observable", "planner", "experiment", "judge")
    lines.extend(_success("null_model", transport, effort="medium"))
    lines.extend(_null_summary(null_result))

    try:
        design = design_observables(
            hypothesis,
            parsed,
            critique,
            null_result,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
            reasoning_effort="medium",
        )
    except ProviderResponseError as exc:
        return _stop(lines, secret, "observable", exc, transport, "planner", "experiment", "judge")
    lines.extend(_success("observable", transport, effort="medium"))
    lines.extend(_observable_summary(design))

    try:
        simulation = plan_simulation(
            hypothesis,
            parsed,
            critique,
            null_result,
            design,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
            reasoning_effort="medium",
        )
    except ProviderResponseError as exc:
        return _stop(lines, secret, "planner", exc, transport, "experiment", "judge")
    lines.extend(_success("planner", transport, effort="medium"))
    lines.append(f"simulation_status: {simulation.status}")
    lines.append("spec_generated: " + ("true" if simulation.spec is not None else "false"))
    lines.append("simulate_http: not called")

    try:
        experiment = design_experiment(
            hypothesis,
            parsed,
            critique,
            null_result,
            design,
            simulation,
            None,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
            reasoning_effort="medium",
        )
    except ProviderResponseError as exc:
        return _stop(lines, secret, "experiment", exc, transport, "judge")
    lines.extend(_success("experiment", transport, effort="medium"))
    lines.extend(_experiment_summary(experiment))

    try:
        verdict = judge_hypothesis(
            hypothesis,
            parsed,
            critique,
            null_result,
            design,
            simulation,
            None,
            experiment,
            None,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
            reasoning_effort="medium",
        )
    except ProviderResponseError as exc:
        return _stop(lines, secret, "judge", exc, transport)
    lines.extend(_success("judge", transport, effort="medium"))
    lines.extend(_verdict_summary(verdict))
    return _emit(lines, secret, ok=True)


def _experiment_summary(result: object) -> list[str]:
    lines = [f"experiment_status: {result.status}"]
    plan = result.experiment
    if plan is None:
        lines.append("resolution_status: none")
        lines.append("controls: none")
    else:
        lines.append(f"resolution_status: {plan.required_resolution.status}")
        lines.append("controls: " + " | ".join(item.name for item in plan.controlled_variables))
        lines.append("safety_notes: " + " | ".join(plan.safety_notes))
    lines.append("experiment_blockers: " + " | ".join(result.blocking_missing_definitions))
    lines.append(f"experiment_summary: {result.summary}")
    return lines


def _verdict_summary(result: object) -> list[str]:
    return [
        f"judge_status: {result.status}",
        f"primary_reason: {result.primary_reason}",
        f"falsifier: {result.falsifier}",
        "required_next_definition: " + (result.required_next_definition or "none"),
        f"delta_over_sigma: {result.delta_over_sigma}",
        "evidence_refs: " + ",".join(result.evidence_refs),
    ]


def _stop(lines, secret, failed, exc, transport, *pending):
    from live_m2_smoke import _emit, _failure

    lines.extend(_failure(failed, exc, transport))
    for name in pending:
        lines.append(f"{name}_http: not sent")
    lines.append("simulate_http: not called")
    return _emit(lines, secret, ok=False)


if __name__ == "__main__":
    raise SystemExit(main())
