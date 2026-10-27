"""Manual replay of one M4 stage from a sanitized checkpoint.

Run it explicitly:

    python scripts/live_m4_replay.py experiment
    python scripts/live_m4_replay.py judge

Importing this module does not call the network. Pytest does not collect it.
There is no retry and no fallback to the stub.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Validate the checkpoint, then call exactly one live stage."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from live_m1_smoke import REQUIRED_MODEL_ID, load_repo_env, preflight_lines
    from live_m2_smoke import _emit
    from live_m4_smoke import _experiment_diagnostic

    from app.config import load_settings
    from app.diagnostics.m4_checkpoint import ReplayRefused, load_replay
    from app.providers.meta import ConfigurationError, ProviderResponseError
    from app.providers.transport import UrllibTransport
    from app.services.experiment import design_experiment
    from app.services.judge import judge_hypothesis
    from app.services.modes import ExecutionMode

    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1 or arguments[0] not in ("experiment", "judge"):
        print("usage: python scripts/live_m4_replay.py experiment|judge")
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
    lines.append("replay_stage: " + arguments[0])
    lines.append("retries: 0")
    checkpoint = root / "tmp" / "live_m4_checkpoint.json"
    try:
        selection = load_replay(checkpoint, arguments[0])
        stored = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (ReplayRefused, json.JSONDecodeError) as exc:
        lines.append(f"replay_refused: {exc}")
        return _emit(lines, secret, ok=False)
    lines.append("checkpoint_validation: success")
    lines.append(f"checkpoint_last_valid_stage: {stored.get('last_valid_stage')}")
    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.append("replay_http: not sent")
        return _emit(lines, secret, ok=False)

    transport = UrllibTransport()
    try:
        if selection.stage == "experiment":
            result = design_experiment(
                selection.hypothesis,
                selection.parser_result,
                selection.critique,
                selection.null_model,
                selection.observables,
                selection.simulation_plan,
                None,
                mode=ExecutionMode.LIVE,
                settings=settings,
                transport=transport,
                reasoning_effort="medium",
            )
            lines.append(f"experiment_http: {transport.last_http_status}")
            lines.append("experiment_validation: success")
            lines.extend(_experiment_report(result))
            _store_experiment(checkpoint, selection, result, secret)
            lines.append("checkpoint_experiment_appended: true")
            lines.extend(_usage_lines("experiment", transport))
        else:
            assert selection.experiment is not None
            verdict = judge_hypothesis(
                selection.hypothesis,
                selection.parser_result,
                selection.critique,
                selection.null_model,
                selection.observables,
                selection.simulation_plan,
                None,
                selection.experiment,
                None,
                mode=ExecutionMode.LIVE,
                settings=settings,
                transport=transport,
                reasoning_effort="medium",
            )
            lines.append(f"judge_http: {transport.last_http_status}")
            lines.append("judge_validation: success")
            lines.extend(_verdict_report(verdict))
            lines.extend(_usage_lines("judge", transport))
    except (ConfigurationError, ProviderResponseError) as exc:
        if selection.stage == "experiment":
            lines.extend(_experiment_diagnostic(exc, transport, secret, root))
        lines.append(f"replay_http: {getattr(transport, 'last_http_status', None)}")
        lines.append(f"replay_error: {exc}")
        lines.extend(_usage_lines(selection.stage, transport))
        lines.append("retries: 0")
        return _emit(lines, secret, ok=False)
    return _emit(lines, secret, ok=True)


def _store_experiment(path, selection, result, secret: str) -> None:
    from app.diagnostics.m4_checkpoint import write_checkpoint

    write_checkpoint(
        path,
        {
            "hypothesis": selection.hypothesis,
            "parser": selection.parser_result,
            "critic": selection.critique,
            "null": selection.null_model,
            "observable": selection.observables,
            "planner": selection.simulation_plan,
            "experiment": result,
        },
        secret=secret,
    )


def _experiment_report(result) -> list[str]:
    plan = result.experiment
    lines = [f"experiment_status: {result.status}"]
    if plan is None:
        lines.extend(
            [
                "experiment_id: none",
                "observable_ids: none",
                "resolution_status: none",
                "resolution_value: none",
                "controls: none",
                "safety_notes: none",
            ]
        )
    else:
        lines.extend(
            [
                f"experiment_id: {plan.experiment_id}",
                "observable_ids: " + ",".join(plan.observable_ids),
                f"resolution_status: {plan.required_resolution.status}",
                f"resolution_value: {plan.required_resolution.value}",
                "controls: " + " | ".join(item.name for item in plan.controlled_variables),
                "safety_notes: " + json.dumps(plan.safety_notes, ensure_ascii=False),
            ]
        )
    lines.append("blockers: " + " | ".join(result.blocking_missing_definitions))
    return lines


def _verdict_report(result) -> list[str]:
    return [
        f"judge_status: {result.status}",
        f"primary_reason: {result.primary_reason}",
        f"falsifier: {result.falsifier}",
        "required_next_definition: " + (result.required_next_definition or "none"),
        f"delta_over_sigma: {result.delta_over_sigma}",
        "evidence_refs: " + ",".join(result.evidence_refs),
    ]


def _usage_lines(prefix: str, transport) -> list[str]:
    usage = getattr(transport, "last_usage", None) or {}

    def value(name: str) -> str:
        item = usage.get(name)
        return "not returned" if item is None else str(item)

    return [
        f"{prefix}_prompt_tokens: {value('prompt_tokens')}",
        f"{prefix}_completion_tokens: {value('completion_tokens')}",
        f"{prefix}_reasoning_tokens: {value('reasoning_tokens')}",
        f"{prefix}_total_tokens: {value('total_tokens')}",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
