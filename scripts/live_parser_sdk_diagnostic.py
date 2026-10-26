"""One parser request through the official OpenAI-compatible SDK.

This is not the production provider. Run it only when the manual schema
diagnostic has not already identified the validation failure:

    python scripts/live_parser_sdk_diagnostic.py

Importing this module does not call the network or import the SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Parse the pendulum hypothesis with response_format=ParserResult."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from live_m1_smoke import HYPOTHESIS, REQUIRED_MODEL_ID, load_repo_env

    from app.config import load_settings
    from app.prompts.parser import PARSER_SYSTEM_PROMPT, parser_user_prompt
    from app.schemas.hypothesis import HypothesisInput
    from app.schemas.parser import ParserResult

    load_repo_env(root)
    settings = load_settings()
    secret = settings.model_api_key.get_secret_value()
    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        print("sdk_parser_http: not sent")
        return 1

    from openai import OpenAI

    hypothesis = HypothesisInput(statement=HYPOTHESIS)
    client = OpenAI(api_key=secret, base_url=settings.meta_base_url)
    completion = client.beta.chat.completions.parse(
        model=settings.meta_model_id,
        messages=[
            {"role": "system", "content": PARSER_SYSTEM_PROMPT},
            {"role": "user", "content": parser_user_prompt(hypothesis.model_dump_json())},
        ],
        response_format=ParserResult,
    )
    choice = completion.choices[0]
    parsed = choice.message.parsed
    usage = completion.usage
    print(f"http_status: 200")
    print(f"model: {completion.model}")
    print(f"finish_reason: {choice.finish_reason}")
    if usage is not None:
        print(f"prompt_tokens: {usage.prompt_tokens}")
        print(f"completion_tokens: {usage.completion_tokens}")
        print(f"total_tokens: {usage.total_tokens}")
    print("validation: " + ("success" if isinstance(parsed, ParserResult) else "failure"))
    print("critic_http: not sent")
    return 0 if isinstance(parsed, ParserResult) else 1


if __name__ == "__main__":
    raise SystemExit(main())
