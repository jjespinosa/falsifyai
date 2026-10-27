"""Manual live canary for milestone M5.

Run it explicitly:

    python scripts/live_m5_smoke.py

It loads the repository-root .env and sends one POST /api/v1/run for the
pendulum hypothesis with reasoning_profile economy. It does not retry.
Importing this module does not call the network.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Send one live run through the application route."""

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
    from app.diagnostics.parser_response import parser_contract_audit
    from app.main import create_app
    from app.providers.transport import UrllibTransport
    from app.schemas.run import RunResult
    from app.services.m2_fixtures import CASE_MASS
    from app.services.run import RunDiagnostics

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
    lines.append("reasoning_profile: economy")
    lines.append("parser_reasoning_effort: minimal")
    audit = parser_contract_audit()
    lines.append(
        "parser_contract: "
        f"claim_id_pattern_sent={str(audit['claim_id_pattern_sent']).lower()} "
        f"assumption_id_pattern_sent={str(audit['assumption_id_pattern_sent']).lower()}"
    )
    for name in audit["absent"]:
        lines.append(f"schema_absent: {name}")
    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.append("run_http: not sent")
        return _emit(lines, secret, ok=False)

    transport = UrllibTransport()
    app = create_app(settings, live_transport=transport)
    parser_response = root / "tmp" / "live_run_parser_response.json"
    checkpoint = root / "tmp" / "live_run_checkpoint.json"
    app.state.run_diagnostics = RunDiagnostics(
        checkpoint_path=checkpoint,
        parser_response_path=parser_response,
        secret=secret,
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/run",
        json={
            "hypothesis": {"statement": CASE_MASS},
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
    verdict = result.verdict.status if result.verdict is not None else "none"
    lines.append(f"verdict: {verdict}")
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
        response_path = parser_response
        if failed.name != "parser":
            response_path = parser_response.with_name(f"live_run_{failed.name}_response.json")
        lines.extend(_parser_file_lines(response_path))
    lines.extend(_checkpoint_lines(checkpoint))
    if failed is not None:
        lines.append(f"stopped_after: {failed.name}")
    return _emit(lines, secret, ok=response.status_code == 200 and result.error is None)


def _parser_file_lines(path: Path) -> list[str]:
    import json

    if not path.is_file():
        return ["raw_response_written: false"]
    document = json.loads(path.read_text(encoding="utf-8"))
    metadata = document.get("metadata") if isinstance(document, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    lines = [
        "raw_response_written: true",
        f"saved_http_status: {metadata.get('http_status')}",
        f"saved_finish_reason: {metadata.get('finish_reason')}",
        f"saved_model: {metadata.get('model')}",
        f"saved_prompt_tokens: {metadata.get('prompt_tokens')}",
        f"saved_completion_tokens: {metadata.get('completion_tokens')}",
        f"saved_reasoning_tokens: {metadata.get('reasoning_tokens')}",
        f"saved_character_count: {metadata.get('character_count')}",
        "saved_top_level_keys: " + ",".join(metadata.get("top_level_keys") or []),
    ]
    errors = document.get("validation_errors") if isinstance(document, dict) else None
    lines.append(f"validation_error_count: {len(errors) if isinstance(errors, list) else 0}")
    if isinstance(errors, list):
        for index, row in enumerate(errors, start=1):
            if not isinstance(row, dict):
                continue
            lines.append(
                f"{index}. path={row.get('path')} type={row.get('type')} "
                f"field={row.get('field')} value_type={row.get('value_type')} "
                f"value={row.get('value')} message={row.get('message')}"
            )
    return lines


def _science_lines(result) -> list[str]:
    claim = result.parser.claims[0] if result.parser is not None and result.parser.claims else None
    lines = []
    if claim is not None:
        lines.append(f"claim_id: {claim.claim_id}")
        lines.append(f"is_operational: {str(claim.is_operational).lower()}")
        for variable in claim.variables:
            lines.append(f"variable: {variable.name} defined={str(variable.defined).lower()}")
        for item in claim.missing_definitions:
            lines.append(
                f"missing_definition: critical={str(item.critical).lower()} {item.statement}"
            )
    null_model = result.null_model.models[0] if result.null_model is not None and result.null_model.models else None
    if null_model is not None:
        lines.append(f"h0: {null_model.description}")
    observable = None
    if result.observable_design is not None:
        observable = next(
            (item for item in result.observable_design.observables if item.discriminating),
            None,
        )
        if observable is None and result.observable_design.observables:
            observable = result.observable_design.observables[0]
    if observable is not None:
        lines.append(
            f"observable: {observable.observable_id} discriminating={str(observable.discriminating).lower()} {observable.name}"
        )
    if result.simulation_plan is not None:
        lines.append(f"simulation_plan_status: {result.simulation_plan.status}")
    if result.experiment is not None:
        lines.append(f"experiment_status: {result.experiment.status}")
    if result.verdict is not None:
        lines.append(f"required_next_definition: {result.verdict.required_next_definition}")
    return lines


def _checkpoint_lines(path: Path) -> list[str]:
    import json

    if not path.is_file():
        return ["checkpoint_written: false", "checkpoint_last_valid_stage: none"]
    document = json.loads(path.read_text(encoding="utf-8"))
    last = document.get("last_valid_stage") if isinstance(document, dict) else None
    return ["checkpoint_written: true", f"checkpoint_last_valid_stage: {last}"]


if __name__ == "__main__":
    raise SystemExit(main())
