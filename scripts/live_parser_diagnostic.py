"""Capture one live parser response and the exact ParserResult validation failure.

Run it explicitly:

    python scripts/live_parser_diagnostic.py

It loads the repository-root .env, sends one parser request, and does not call
the critic. Importing this module does not call the network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    """Send one parser request and print a sanitized validation diagnostic."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    scripts = root / "scripts"
    for entry in (str(backend), str(scripts)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    from live_m1_smoke import HYPOTHESIS, REQUIRED_MODEL_ID, load_repo_env, preflight_lines

    from app.config import load_settings
    from app.diagnostics.parser_response import (
        compare_parser_schemas,
        completion_facts,
        content_profile,
        redact,
        render_validation_diagnostic,
        write_structured_response,
    )
    from app.prompts.parser import PARSER_SYSTEM_PROMPT, parser_user_prompt
    from app.providers.meta import ConfigurationError, ProviderResponseError
    from app.providers.schema_json import strict_json_schema
    from app.providers.transport import UrllibTransport
    from app.schemas.hypothesis import HypothesisInput
    from app.schemas.parser import ParserResult
    from pydantic import ValidationError

    env_detected = load_repo_env(root)
    settings = load_settings()
    secret = settings.model_api_key.get_secret_value()
    lines = preflight_lines(
        env_detected=env_detected,
        key=secret,
        base_url=settings.meta_base_url,
        model_id=settings.meta_model_id,
    )
    schema_report = compare_parser_schemas()
    lines.append("schema_sent_equals_transformed: " + str(schema_report["sent_equals_transformed"]).lower())
    lines.append("schema_raw_refs: " + str(schema_report["raw_ref_count"]))
    lines.append("schema_sent_refs: " + str(schema_report["transformed_ref_count"]))
    for difference in schema_report["differences"]:
        lines.append("schema_difference: " + difference)

    if secret.strip() == "" or settings.meta_model_id != REQUIRED_MODEL_ID:
        lines.append("parser_http: not sent")
        lines.append("validation: not reached")
        return _emit(lines, secret)
    hypothesis = HypothesisInput(statement=HYPOTHESIS)
    transport = UrllibTransport()
    try:
        from app.providers.meta import MetaModelProvider

        provider = MetaModelProvider(settings, transport=transport)
        completion = provider.complete(
            system=PARSER_SYSTEM_PROMPT,
            user=parser_user_prompt(hypothesis.model_dump_json()),
            response_schema=strict_json_schema(ParserResult),
            schema_name="ParserResult",
        )
    except (ConfigurationError, ProviderResponseError) as exc:
        status = getattr(exc, "http_status", None)
        lines.append(f"parser_http: failure{'' if status is None else ' ' + str(status)}")
        lines.append(f"parser_error: {exc}")
        lines.append("validation: not reached")
        lines.append("critic_http: not sent")
        return _emit(lines, secret)

    facts = completion_facts(transport.last_body, http_status=transport.last_http_status or 200)
    lines.extend(
        [
            f"http_status: {facts['http_status']}",
            f"model: {facts['model'] or settings.meta_model_id}",
            f"finish_reason: {facts['finish_reason'] or '(missing)'}",
            f"prompt_tokens: {facts['prompt_tokens']}",
            f"completion_tokens: {facts['completion_tokens']}",
            f"total_tokens: {facts['total_tokens']}",
            "critic_http: not sent",
        ]
    )
    destination = root / "tmp" / "live_parser_response.json"
    write_structured_response(destination, completion.content, secret=secret)
    lines.append(f"saved_response: {destination}")
    lines.append(f"raw_content_characters: {len(completion.content)}")
    try:
        payload = json.loads(completion.content)
    except json.JSONDecodeError as exc:
        lines.append("validation: failure")
        lines.append(f"json_error: {exc.msg} at position {exc.pos}")
        return _emit(lines, secret)

    profile = content_profile(payload, completion.content)
    lines.append("top_level_keys: " + ",".join(profile["top_level_keys"]))
    lines.append(f"claims: {profile['claims']}")
    lines.append(f"assumptions: {profile['assumptions']}")
    lines.append(f"undefined_terms: {profile['undefined_terms']}")
    lines.append(f"parser_notes: {profile['parser_notes']}")
    for path, count in profile["array_lengths"].items():
        lines.append(f"array {path}: {count}")
    for item in profile["longest_strings"]:
        lines.append(f"string {item['path']}: {item['length']} chars")

    try:
        ParserResult.model_validate(payload)
    except ValidationError as exc:
        lines.append("validation: failure")
        lines.append(render_validation_diagnostic(exc))
        lines.append("response_json:")
        lines.append(json.dumps(payload, indent=2, ensure_ascii=False))
        return _emit(lines, secret)

    lines.append("validation: success")
    return _emit(lines, secret)


def _emit(lines: list[str], secret: str) -> int:
    from app.diagnostics.parser_response import redact

    rendered = redact("\n".join(lines), secret)
    if secret and secret in rendered:
        print("diagnostic refused to print because the report still contained the API key")
        return 3
    print(rendered)
    return 0 if "validation: success" in rendered else 1


if __name__ == "__main__":
    raise SystemExit(main())
