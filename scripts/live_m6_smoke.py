"""Manual live canaries for milestone M6.

Run one case explicitly:

    python scripts/live_m6_smoke.py duffing
    python scripts/live_m6_smoke.py dq12

Each invocation loads the repository-root .env and sends one POST /api/v1/run
with reasoning_profile economy. It does not retry. Importing this module does
not call the network.
"""

from __future__ import annotations

import sys
from pathlib import Path


CASES = ("duffing", "dq12")


def main(argv: list[str] | None = None) -> int:
    """Send one live run for the named M6 statement."""

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in CASES:
        print("usage: python scripts/live_m6_smoke.py duffing|dq12")
        return 2
    case = args[0]

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from fastapi.testclient import TestClient

    from live_m1_smoke import REQUIRED_MODEL_ID, load_repo_env, preflight_lines
    from live_m2_smoke import _emit

    from app.config import load_settings
    from app.main import create_app
    from app.providers.transport import UrllibTransport
    from app.schemas.run import RunResult
    from app.services.m6_fixtures import CASE_DQ12, CASE_DUFFING
    from app.services.run import RunDiagnostics

    statement = CASE_DUFFING if case == "duffing" else CASE_DQ12
    env_detected = load_repo_env(root)
    settings = load_settings()
    secret = settings.model_api_key.get_secret_value()
    lines = [f"case: {case}"]
    lines.extend(
        preflight_lines(
            env_detected=env_detected,
            key=secret,
            base_url=settings.meta_base_url,
            model_id=settings.meta_model_id,
        )
    )
    lines.append("retries: 0")
    lines.append("reasoning_profile: economy")
    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.append("run_http: not sent")
        return _emit(lines, secret, ok=False)

    transport = UrllibTransport()
    app = create_app(settings, live_transport=transport)
    tmp = root / "tmp"
    tmp.mkdir(exist_ok=True)
    parser_response = tmp / f"live_m6_{case}_parser_response.json"
    checkpoint = tmp / f"live_m6_{case}_checkpoint.json"
    app.state.run_diagnostics = RunDiagnostics(
        checkpoint_path=checkpoint,
        parser_response_path=parser_response,
        secret=secret,
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/run",
        json={
            "hypothesis": {"statement": statement},
            "mode": "live",
            "reasoning_profile": "economy",
        },
    )
    lines.append(f"run_http: {response.status_code}")
    try:
        result = RunResult.model_validate(response.json())
    except Exception as exc:
        lines.append(f"run_validation: failure {exc}")
        return _emit(lines, secret, ok=False)
    lines.append("run_validation: success")
    lines.append(f"run_status: {result.status}")
    for stage in result.stages:
        lines.append(f"stage_{stage.name}: {stage.status}")
        lines.append(
            f"stage_{stage.name}_tokens: prompt={stage.prompt_tokens} "
            f"completion={stage.completion_tokens} reasoning={stage.reasoning_tokens} "
            f"total={stage.total_tokens}"
        )
    lines.extend(_science_lines(result))
    lines.append(f"model_calls: {result.usage.model_calls}")
    lines.append(f"prompt_tokens: {result.usage.prompt_tokens}")
    lines.append(f"completion_tokens: {result.usage.completion_tokens}")
    lines.append(f"reasoning_tokens: {result.usage.reasoning_tokens}")
    lines.append(f"total_tokens: {result.usage.total_tokens}")
    if result.failure is not None:
        lines.append(f"failure_stage: {result.failure.stage}")
        lines.append(f"failure_kind: {result.failure.failure_kind}")
        lines.append(f"safe_message: {result.failure.safe_message}")
        for path in result.failure.validation_paths:
            lines.append(f"validation_path: {path}")
    if result.error:
        lines.append(f"run_error: {result.error}")
    failed = next((stage for stage in result.stages if stage.status == "failed"), None)
    if failed is None:
        lines.append("raw_response_written: false")
    else:
        lines.append(f"checkpoint: {checkpoint}")
        lines.append("raw_response_written: true")
    ok = response.status_code == 200 and result.error is None and failed is None
    return _emit(lines, secret, ok=ok)


def _science_lines(result) -> list[str]:
    lines: list[str] = []
    claim = result.parser.claims[0] if result.parser and result.parser.claims else None
    if claim is not None:
        lines.append(f"claim_operational: {str(claim.is_operational).lower()}")
        for item in claim.missing_definitions:
            lines.append(f"missing_definition: {item.statement}")
    null_model = result.null_model.models[0] if result.null_model and result.null_model.models else None
    if null_model is not None:
        lines.append(f"h0: {null_model.description}")
    observable = None
    if result.observable_design and result.observable_design.observables:
        observable = next(
            (item for item in result.observable_design.observables if item.discriminating),
            result.observable_design.observables[0],
        )
        lines.append(
            f"observable: {observable.observable_id} discriminating={str(observable.discriminating).lower()}"
        )
    elif result.observable_design is not None:
        lines.append("observable: none")
    plan = result.simulation_plan.status if result.simulation_plan is not None else "none"
    lines.append(f"simulation_plan_status: {plan}")
    executed = result.simulation_result is not None
    lines.append(f"simulation_executed: {str(executed).lower()}")
    if executed:
        separation = max(abs(value) for value in result.simulation_result.delta)
        lines.append(f"h0_h1_separation: {separation}")
        lines.append(f"simulation_id: {result.simulation_result.simulation_id}")
    experiment = result.experiment.status if result.experiment is not None else "none"
    lines.append(f"experiment_status: {experiment}")
    if result.verdict is not None:
        lines.append(f"verdict: {result.verdict.status}")
        lines.append(f"delta_over_sigma: {result.verdict.delta_over_sigma}")
        lines.append(f"required_next_definition: {result.verdict.required_next_definition}")
    else:
        lines.append("verdict: none")
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
