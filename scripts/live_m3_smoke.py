"""Manual live canary for milestone M3.

Run it explicitly:

    python scripts/live_m3_smoke.py

It loads the repository-root .env and runs parser, critic, null model,
observable designer, and simulation planner once each. It stops at the first
failure, does not retry, and does not call /simulate when the plan is blocked.
Importing this module does not call the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

CASE_MASS = (
    "At fixed pendulum length and within the small-angle regime, "
    "increasing the bob mass changes the oscillation period."
)


def main() -> int:
    """Run the implemented chain through the simulation planner."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from live_m1_smoke import REQUIRED_MODEL_ID, load_repo_env, preflight_lines
    from live_m2_smoke import (
        _emit,
        _failure,
        _null_summary,
        _observable_summary,
        _success,
    )

    from app.config import load_settings
    from app.providers.meta import ConfigurationError, ProviderResponseError
    from app.providers.transport import UrllibTransport
    from app.schemas.hypothesis import HypothesisInput
    from app.services.critic import critique_hypothesis
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
        lines.extend(_failure("parser", exc, transport))
        lines.append("critic_http: not sent")
        lines.append("null_model_http: not sent")
        lines.append("observable_http: not sent")
        lines.append("planner_http: not sent")
        lines.append("simulate_http: not called")
        return _emit(lines, secret, ok=False)
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
        lines.extend(_failure("critic", exc, transport))
        lines.append("null_model_http: not sent")
        lines.append("observable_http: not sent")
        lines.append("planner_http: not sent")
        lines.append("simulate_http: not called")
        return _emit(lines, secret, ok=False)
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
        lines.extend(_failure("null_model", exc, transport))
        lines.append("observable_http: not sent")
        lines.append("planner_http: not sent")
        lines.append("simulate_http: not called")
        return _emit(lines, secret, ok=False)
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
        lines.extend(_failure("observable", exc, transport))
        lines.append("planner_http: not sent")
        lines.append("simulate_http: not called")
        return _emit(lines, secret, ok=False)
    lines.extend(_success("observable", transport, effort="medium"))
    lines.extend(_observable_summary(design))

    try:
        plan = plan_simulation(
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
        lines.extend(_failure("planner", exc, transport))
        lines.append("simulate_http: not called")
        return _emit(lines, secret, ok=False)
    lines.extend(_success("planner", transport, effort="medium"))
    lines.append(f"planner_status: {plan.status}")
    lines.append("spec_generated: " + ("true" if plan.spec is not None else "false"))
    lines.append("planner_observable: " + (plan.observable_id or "none"))
    lines.append("blockers: " + " | ".join(plan.blocking_missing_definitions))
    lines.append(f"planner_summary: {plan.summary}")
    lines.append("simulate_http: not called")
    return _emit(lines, secret, ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
