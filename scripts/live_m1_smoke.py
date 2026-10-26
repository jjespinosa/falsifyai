"""Manual live canary for milestone M1.

Run it explicitly with the project virtualenv:

    python scripts/live_m1_smoke.py

On execution it loads the repository-root ``.env`` without overriding variables
already set in the process. Importing this module does not read that file,
open a socket, or call the model. Pytest does not collect it. The application
does not import it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

HYPOTHESIS = (
    "For a simple pendulum in the small-angle regime, increasing the pendulum "
    "length increases the oscillation period."
)
REQUIRED_MODEL_ID = "muse-spark-1.3"
_KEY_PREFIX = "LLM_"


def repo_root() -> Path:
    """Return the repository root that contains this script."""

    return Path(__file__).resolve().parents[1]


def env_file(root: Path | None = None) -> Path:
    """Return the ``.env`` path for a repository root."""

    return (root or repo_root()) / ".env"


def load_repo_env(root: Path | None = None) -> bool:
    """Load ``.env`` from the repository root.

    Variables already present in the process environment stay as they are.
    """

    path = env_file(root)
    detected = path.is_file()
    if detected:
        load_dotenv(path, override=False)
    return detected


def preflight_lines(*, env_detected: bool, key: str, base_url: str, model_id: str) -> list[str]:
    """Describe configuration without including the API key."""

    present = bool(key.strip())
    return [
        f"MODEL_API_KEY present: {str(present).lower()}",
        f"key prefix valid: {str(present and key.startswith(_KEY_PREFIX)).lower()}",
        f"key length: {len(key)}",
        f"META_BASE_URL: {base_url or '(missing)'}",
        f"META_MODEL_ID: {model_id or '(missing)'}",
        f".env file detected: {str(env_detected).lower()}",
    ]


def main() -> int:
    """Send one parser request and, if it validates, one critic request."""

    root = repo_root()
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    env_detected = load_repo_env(root)

    from app.config import load_settings
    from app.providers.meta import ConfigurationError, ProviderResponseError
    from app.providers.transport import UrllibTransport
    from app.schemas.critic import CritiqueReport
    from app.schemas.hypothesis import HypothesisInput
    from app.schemas.parser import ParserResult
    from app.services.critic import critique_hypothesis
    from app.services.modes import ExecutionMode
    from app.services.parser import parse_hypothesis

    settings = load_settings()
    secret = settings.model_api_key.get_secret_value()
    lines = preflight_lines(
        env_detected=env_detected,
        key=secret,
        base_url=settings.meta_base_url,
        model_id=settings.meta_model_id,
    )
    lines.append(f"model_id: {settings.meta_model_id or '(missing)'}")

    if secret.strip() == "":
        lines.extend(
            [
                "parser_http: not sent",
                "parser_validation: not reached",
                "critic_http: not sent",
                "critic_validation: not reached",
                "error: MODEL_API_KEY is missing",
            ]
        )
        return _finish(lines, secret)
    if settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.extend(
            [
                "parser_http: not sent",
                "parser_validation: not reached",
                "critic_http: not sent",
                "critic_validation: not reached",
                f"error: this canary only calls {REQUIRED_MODEL_ID}",
            ]
        )
        return _finish(lines, secret)

    hypothesis = HypothesisInput(statement=HYPOTHESIS)
    transport = UrllibTransport()
    try:
        parsed = parse_hypothesis(
            hypothesis,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
        )
    except ConfigurationError as exc:
        lines.extend(_stopped("parser", exc, sent=False))
        return _finish(lines, secret)
    except ProviderResponseError as exc:
        lines.extend(_stopped("parser", exc, sent=True))
        lines.append(f"parser_tokens: {_tokens(transport.last_usage)}")
        lines.extend(
            [
                "critic_http: not sent",
                "critic_validation: not reached",
            ]
        )
        return _finish(lines, secret)

    try:
        checked = ParserResult.model_validate(parsed.model_dump())
    except Exception as exc:
        lines.extend(
            [
                "parser_http: success",
                "parser_validation: failure",
                f"parser_error: {exc}",
                f"parser_tokens: {_tokens(transport.last_usage)}",
                "critic_http: not sent",
                "critic_validation: not reached",
            ]
        )
        return _finish(lines, secret)

    lines.extend(
        [
            "parser_http: success",
            "parser_validation: success",
            f"parser_tokens: {_tokens(transport.last_usage)}",
            f"parser_visible_characters: {getattr(transport, 'last_visible_characters', None)}",
            *_parser_summary(checked),
        ]
    )

    try:
        report = critique_hypothesis(
            hypothesis,
            checked,
            mode=ExecutionMode.LIVE,
            settings=settings,
            transport=transport,
        )
    except ProviderResponseError as exc:
        lines.extend(_stopped("critic", exc, sent=True))
        lines.append(f"critic_tokens: {_tokens(transport.last_usage)}")
        return _finish(lines, secret)

    try:
        checked_report = CritiqueReport.model_validate(report.model_dump())
    except Exception as exc:
        lines.extend(
            [
                "critic_http: success",
                "critic_validation: failure",
                f"critic_error: {exc}",
                f"critic_tokens: {_tokens(transport.last_usage)}",
            ]
        )
        return _finish(lines, secret)

    known = {claim.claim_id for claim in checked.claims}
    unknown = sorted(_unknown_claim_ids(checked_report, known))
    lines.extend(
        [
            "critic_http: success",
            "critic_validation: success" if not unknown else "critic_validation: failure",
            f"critic_tokens: {_tokens(transport.last_usage)}",
            f"critic_visible_characters: {getattr(transport, 'last_visible_characters', None)}",
            *_critic_summary(checked_report, unknown),
        ]
    )
    return _finish(lines, secret, ok=not unknown)


def _stopped(name: str, exc: BaseException, *, sent: bool) -> list[str]:
    status = getattr(exc, "http_status", None)
    stage = getattr(exc, "stage", None)
    if not sent:
        http = "not sent"
        validation = "not reached"
    elif stage == "validation" and status is None:
        http = "success"
        validation = "failure"
    else:
        http = f"failure{'' if status is None else ' ' + str(status)}"
        validation = "not reached"
    return [
        f"{name}_http: {http}",
        f"{name}_validation: {validation}",
        f"{name}_error: {exc}",
    ]


def _parser_summary(result: object) -> list[str]:
    claims = result.claims
    lines = [
        f"claims: {len(claims)}",
        "claim_ids: " + ",".join(claim.claim_id for claim in claims),
    ]
    for claim in claims:
        critical = sum(1 for item in claim.missing_definitions if item.critical)
        lines.append(
            f"{claim.claim_id}: type={claim.claim_type.value} "
            f"operational={str(claim.is_operational).lower()} "
            f"origin={claim.provenance.origin.value} "
            f"epistemic_status={claim.epistemic_status.value} "
            f"critical_missing={critical} "
            f"missing_definitions={len(claim.missing_definitions)} "
            f"confidence={claim.confidence.value}"
        )
    lines.append(f"assumptions: {len(result.assumptions)}")
    lines.append(f"undefined_terms: {len(result.undefined_terms)}")
    return lines


def _critic_summary(report: object, unknown: list[str]) -> list[str]:
    lines = [
        "affected_claim_ids: " + ("only parser claims" if not unknown else "unknown " + ",".join(unknown)),
        (
            "issues: "
            f"blocking={len(report.blocking_issues)} "
            f"major={len(report.major_issues)} "
            f"minor={len(report.minor_issues)}"
        ),
        f"conventional_explanations: {len(report.conventional_explanations)}",
    ]
    return lines


def _unknown_claim_ids(report: object, known: set[str]) -> set[str]:
    found: set[str] = set()
    for issue in report.issues:
        found.update(claim_id for claim_id in issue.affected_claim_ids if claim_id not in known)
    for explanation in report.conventional_explanations:
        found.update(
            claim_id for claim_id in explanation.affected_claim_ids if claim_id not in known
        )
    return found


def _tokens(usage: dict[str, int] | None) -> str:
    if not usage:
        return "not returned"
    return " ".join(f"{key}={usage[key]}" for key in usage)


def _finish(lines: list[str], secret: str, *, ok: bool = False) -> int:
    rendered = "\n".join(lines)
    if secret:
        rendered = rendered.replace(secret, "[redacted]")
    rendered = re.sub(r"Bearer\s+\S+", "Bearer [redacted]", rendered)
    if secret and secret in rendered:
        print("LIVE CANARY: refused to print because the report still contained the API key")
        return 3
    print(rendered)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
