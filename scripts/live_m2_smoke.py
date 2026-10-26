"""Manual live canary for milestone M2.

Run it explicitly:

    python scripts/live_m2_smoke.py

It loads the repository-root .env and runs parser, critic, null model, and
observable designer once each. It stops at the first failure and does not
retry. Importing this module does not call the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

CASE_MASS = (
    "At fixed pendulum length and within the small-angle regime, "
    "increasing the bob mass changes the oscillation period."
)


def main() -> int:
    """Run the four implemented stages on the mass-and-period hypothesis."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from live_m1_smoke import REQUIRED_MODEL_ID, load_repo_env, preflight_lines

    from app.config import load_settings
    from app.providers.meta import ConfigurationError, ProviderResponseError
    from app.providers.transport import UrllibTransport
    from app.schemas.hypothesis import HypothesisInput
    from app.services.critic import critique_hypothesis
    from app.services.modes import ExecutionMode
    from app.services.null_model import build_null_model
    from app.services.observable import design_observables
    from app.services.parser import parse_hypothesis

    env_detected = load_repo_env(root)
    settings = load_settings()
    secret = settings.model_api_key.get_secret_value()
    lines = preflight_lines(
        env_detected=env_detected,
        key=secret,
        base_url=settings.meta_base_url,
        model_id=settings.meta_model_id,
    )
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
        return _emit(lines, secret, ok=False)
    lines.extend(_success("parser", transport, effort="minimal"))
    lines.append("claim_ids: " + ",".join(claim.claim_id for claim in parsed.claims))

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
        return _emit(lines, secret, ok=False)
    lines.extend(_success("critic", transport, effort="low"))
    lines.append(
        "critic_issues: "
        f"blocking={len(critique.blocking_issues)} "
        f"major={len(critique.major_issues)} "
        f"minor={len(critique.minor_issues)}"
    )

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
        return _emit(lines, secret, ok=False)
    lines.extend(_success("observable", transport, effort="medium"))
    lines.extend(_observable_summary(design))
    return _emit(lines, secret, ok=True)


def _success(name: str, transport: object, *, effort: str) -> list[str]:
    usage = getattr(transport, "last_usage", None) or {}
    return [
        f"{name}_http: success {getattr(transport, 'last_http_status', None)}",
        f"{name}_validation: success",
        f"{name}_reasoning_effort: {effort}",
        f"{name}_tokens: {_tokens(usage)}",
        f"{name}_visible_characters: {getattr(transport, 'last_visible_characters', None)}",
    ]


def _failure(name: str, exc: BaseException, transport: object) -> list[str]:
    status = getattr(exc, "http_status", None)
    stage = getattr(exc, "stage", None)
    if stage == "validation" and status is None:
        http = "success"
        validation = "failure"
    else:
        http = f"failure{'' if status is None else ' ' + str(status)}"
        validation = "not reached"
    usage = getattr(transport, "last_usage", None) or {}
    return [
        f"{name}_http: {http}",
        f"{name}_validation: {validation}",
        f"{name}_error: {exc}",
        f"{name}_tokens: {_tokens(usage)}",
    ]


def _null_summary(result: object) -> list[str]:
    lines = [f"null_models: {len(result.models)}"]
    for model in result.models:
        lines.append(f"h0_id: {model.model_id}")
        lines.append(f"h0_summary: {model.description}")
        lines.append(f"can_mimic_claim: {str(model.can_mimic_claim).lower()}")
        lines.append("confounders: " + ",".join(model.known_confounders))
        lines.append("blockers: " + ",".join(model.blocking_missing_definitions))
    if not result.models:
        lines.append(f"h0_summary: {result.summary}")
    return lines


def _observable_summary(result: object) -> list[str]:
    lines = [
        f"observable_count: {len(result.observables)}",
        "observable_ids: " + ",".join(item.observable_id for item in result.observables),
        "discriminating: "
        + ",".join(f"{item.observable_id}={str(item.discriminating).lower()}" for item in result.observables),
        "required_controls: "
        + " | ".join(
            f"{item.observable_id}:{' ; '.join(item.required_controls)}" for item in result.observables
        ),
        "observable_blockers: " + ",".join(result.blocking_issues),
        f"observable_summary: {result.summary}",
    ]
    return lines


def _tokens(usage: dict[str, int]) -> str:
    if not usage:
        return "not returned"
    return " ".join(f"{key}={usage[key]}" for key in usage)


def _emit(lines: list[str], secret: str, *, ok: bool) -> int:
    from app.diagnostics.parser_response import redact

    rendered = redact("\n".join(lines), secret)
    if secret and secret in rendered:
        print("diagnostic refused to print because the report still contained the API key")
        return 3
    print(rendered)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
