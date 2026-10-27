"""Manual resume of an M5 run from a sanitized checkpoint.

Run it explicitly:

    python scripts/live_m5_resume.py --from parser
    python scripts/live_m5_resume.py --from critic
    python scripts/live_m5_resume.py --from null_model
    python scripts/live_m5_resume.py --from observable
    python scripts/live_m5_resume.py --from simulation_plan
    python scripts/live_m5_resume.py --from experiment

Importing this module does not call the network. Pytest does not collect it.
There is no retry and no fallback to the stub.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Validate the checkpoint, then continue from the requested stage once."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from live_m1_smoke import REQUIRED_MODEL_ID, load_repo_env, preflight_lines
    from live_m2_smoke import _emit

    from app.config import load_settings
    from app.diagnostics.run_checkpoint import (
        ResumeRefused,
        build_resume_request,
        load_resume,
        parse_resume_args,
    )
    from app.providers.transport import UrllibTransport
    from app.services.modes import ExecutionMode
    from app.services.run import RunDiagnostics, execute_run

    try:
        stage, checkpoint_override = parse_resume_args(list(sys.argv[1:] if argv is None else argv))
    except ResumeRefused as exc:
        print(exc)
        return 2

    checkpoint = checkpoint_override or (root / "tmp" / "live_run_checkpoint.json")
    try:
        selection = load_resume(checkpoint, stage)
    except ResumeRefused as exc:
        print(f"resume_refused: {exc}")
        return 2

    env_detected = load_repo_env(root)
    settings = load_settings()
    secret = settings.model_api_key.get_secret_value()
    lines = preflight_lines(
        env_detected=env_detected,
        key=secret,
        base_url=settings.meta_base_url,
        model_id=settings.meta_model_id,
    )
    lines.append(f"resume_from: {selection.start}")
    lines.append("retries: 0")
    lines.append("reasoning_profile: economy")
    request = build_resume_request(selection)
    if request.mode is not ExecutionMode.LIVE:
        lines.append("resume_refused: resume does not fall back to stub")
        return _emit(lines, secret, ok=False)
    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.append("resume_http: not sent")
        return _emit(lines, secret, ok=False)

    result = execute_run(
        request,
        settings=settings,
        transport=UrllibTransport(),
        diagnostics=RunDiagnostics(
            checkpoint_path=checkpoint,
            parser_response_path=root / "tmp" / "live_run_parser_response.json",
            secret=secret,
        ),
        resume=selection,
    )
    lines.append(f"run_status: {result.status}")
    for stage_record in result.stages:
        lines.append(f"stage_{stage_record.name}: {stage_record.status}")
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
    return _emit(lines, secret, ok=result.error is None)


if __name__ == "__main__":
    raise SystemExit(main())
