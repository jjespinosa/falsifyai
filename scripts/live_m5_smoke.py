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
    from app.main import create_app
    from app.providers.transport import UrllibTransport
    from app.schemas.run import RunResult
    from app.services.m2_fixtures import CASE_MASS

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
    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.append("run_http: not sent")
        return _emit(lines, secret, ok=False)

    transport = UrllibTransport()
    client = TestClient(create_app(settings, live_transport=transport))
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
    verdict = result.verdict.status if result.verdict is not None else "none"
    lines.append(f"verdict: {verdict}")
    lines.append(f"model_calls: {result.usage.model_calls}")
    lines.append(f"prompt_tokens: {result.usage.prompt_tokens}")
    lines.append(f"completion_tokens: {result.usage.completion_tokens}")
    lines.append(f"reasoning_tokens: {result.usage.reasoning_tokens}")
    lines.append(f"total_tokens: {result.usage.total_tokens}")
    if result.error:
        lines.append(f"run_error: {result.error}")
    return _emit(lines, secret, ok=response.status_code == 200 and result.error is None)


if __name__ == "__main__":
    raise SystemExit(main())
