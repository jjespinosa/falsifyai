"""Sanitized diagnostics for an ExperimentPlanResult that failed validation.

These helpers do not call the network, do not read environment variables,
and do not rewrite a model payload into a valid plan.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.diagnostics.parser_response import _schema_differences
from app.providers.schema_json import strict_json_schema
from app.schemas.experiment import (
    ExperimentPlan,
    ExperimentPlanResult,
    ExperimentVariable,
    ParameterScan,
    RequiredResolution,
)
from app.schemas.verdict import ExperimentalCapability, FalsificationVerdict

_VALIDATED_MODELS: tuple[type[BaseModel], ...] = (
    ExperimentVariable,
    ParameterScan,
    RequiredResolution,
    ExperimentPlan,
    ExperimentPlanResult,
    ExperimentalCapability,
    FalsificationVerdict,
)
_VALUE_LIMIT = 240


@dataclass(frozen=True)
class SemanticRule:
    """One custom validator and whether the JSON Schema sent to Meta enforces it."""

    model: str
    validator: str
    kind: str
    rule: str
    in_json_schema: bool
    why: str


def describe_validation_error(exc: ValidationError, *, secret: str = "") -> list[dict[str, str]]:
    """Return every Pydantic error, including a redacted value when that is safe."""

    rows: list[dict[str, str]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        path = ".".join(str(part) for part in location)
        rows.append(
            {
                "path": path,
                "type": str(error.get("type", "")),
                "message": str(error.get("msg", "")),
                "field": str(location[-1]) if location else "",
                "value_type": type(error.get("input")).__name__,
                "value": _safe_value(error.get("input"), secret),
            }
        )
    return rows


def render_validation_errors(exc: ValidationError, *, secret: str = "") -> str:
    """Format every validation error. Pydantic's list is not truncated."""

    rows = describe_validation_error(exc, secret=secret)
    lines = [f"validation_errors: {len(rows)}"]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"{index}.",
                f"path: {row['path']}",
                f"type: {row['type']}",
                f"message: {row['message']}",
                f"field: {row['field']}",
                f"value_type: {row['value_type']}",
                f"value: {row['value']}",
            ]
        )
    return "\n".join(lines)


def message_content(body: object) -> str | None:
    """Return the assistant message content and nothing else from a completion body."""

    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    return None


def safe_metadata(body: object, *, http_status: int | None) -> dict[str, Any]:
    """Status, model, finish reason, and integer token counts. No headers."""

    model = None
    finish_reason = None
    usage: dict[str, int] = {}
    if isinstance(body, dict):
        model_value = body.get("model")
        if isinstance(model_value, str):
            model = model_value
        choices = body.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            reason = choices[0].get("finish_reason")
            if isinstance(reason, str):
                finish_reason = reason
        raw_usage = body.get("usage")
        if isinstance(raw_usage, dict):
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = raw_usage.get(key)
                if isinstance(value, int):
                    usage[key] = value
            details = raw_usage.get("completion_tokens_details")
            if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), int):
                usage["reasoning_tokens"] = details["reasoning_tokens"]
    return {
        "http_status": http_status,
        "model": model,
        "finish_reason": finish_reason,
        "usage": usage,
    }


def experiment_profile(payload: object, raw_text: str) -> dict[str, Any]:
    """Counts and presence flags for one structured experiment response."""

    top_level = sorted(payload) if isinstance(payload, dict) else []
    status = payload.get("status") if isinstance(payload, dict) else None
    experiment = payload.get("experiment") if isinstance(payload, dict) else None
    blockers = payload.get("blocking_missing_definitions") if isinstance(payload, dict) else None
    resolution = experiment.get("required_resolution") if isinstance(experiment, dict) else None
    return {
        "character_count": len(raw_text),
        "top_level_keys": top_level,
        "status": status if isinstance(status, str) else None,
        "experiment_is_null": experiment is None,
        "blocker_count": len(blockers) if isinstance(blockers, list) else None,
        "required_resolution_exists": isinstance(resolution, dict),
        "required_resolution_status": (
            resolution.get("status") if isinstance(resolution, dict) else None
        ),
        "required_resolution_value_type": (
            type(resolution.get("value")).__name__ if isinstance(resolution, dict) else None
        ),
        "falsifier_candidate_exists": (
            isinstance(experiment, dict) and "falsifier_candidate" in experiment
        ),
        "array_counts": _array_counts(payload if isinstance(payload, dict) else {}, experiment),
    }


def render_experiment_profile(profile: dict[str, Any]) -> str:
    """One line per fact the diagnostic report needs."""

    counts = profile["array_counts"]
    keys = ",".join(profile["top_level_keys"])
    lines = [
        f"raw_chars: {profile['character_count']}",
        f"top_level_keys: {keys}",
        f"experiment_status_value: {profile['status']}",
        "experiment_is_null: " + ("true" if profile["experiment_is_null"] else "false"),
        f"blocker_count: {profile['blocker_count']}",
        "required_resolution_exists: "
        + ("true" if profile["required_resolution_exists"] else "false"),
        f"required_resolution_status_value: {profile['required_resolution_status']}",
        f"required_resolution_value_type: {profile['required_resolution_value_type']}",
        "falsifier_candidate_exists: "
        + ("true" if profile["falsifier_candidate_exists"] else "false"),
    ]
    for name in (
        "controlled_variables",
        "control_groups",
        "confounders",
        "procedure_outline",
        "limitations",
        "parameter_scan",
        "independent_variables",
        "measured_variables",
        "safety_notes",
        "blocking_missing_definitions",
    ):
        lines.append(f"count_{name}: {counts.get(name)}")
    return "\n".join(lines)


def write_experiment_response(
    path: Path,
    raw_content: str,
    metadata: dict[str, Any],
    *,
    secret: str,
) -> None:
    """Save the structured message and safe metadata. Refuse a leftover secret."""

    parsed: object
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        parsed = None
    document: dict[str, Any] = {"metadata": metadata, "character_count": len(raw_content)}
    if isinstance(parsed, (dict, list)):
        document["content"] = parsed
    else:
        document["content_text"] = raw_content
    _write_redacted(path, document, secret)


def compare_experiment_schemas() -> dict[str, Any]:
    """Compare the Pydantic schema, the inlined schema, and the schema sent to Meta.

    The provider sends the transformed schema unchanged.
    """

    raw = ExperimentPlanResult.model_json_schema()
    transformed = strict_json_schema(ExperimentPlanResult)
    sent = transformed
    return {
        "sent_equals_transformed": sent == transformed,
        "raw_ref_count": json.dumps(raw).count('"$ref"'),
        "transformed_ref_count": json.dumps(transformed).count('"$ref"'),
        "differences": _schema_differences(raw, transformed),
        "sent_patterns": _patterns(transformed),
        "sent_nullable": _nullable_fields(transformed),
        "sent_enums": _enum_fields(transformed),
    }


def render_schema_comparison() -> str:
    """Text form of the schema comparison. It does not edit the schema."""

    report = compare_experiment_schemas()
    lines = [
        "schema_sent_equals_transformed: "
        + ("true" if report["sent_equals_transformed"] else "false"),
        f"schema_raw_ref_count: {report['raw_ref_count']}",
        f"schema_transformed_ref_count: {report['transformed_ref_count']}",
        f"schema_difference_count: {len(report['differences'])}",
    ]
    lines.extend(f"schema_difference: {item}" for item in report["differences"])
    lines.append("schema_sent_patterns: " + ",".join(report["sent_patterns"]))
    lines.append("schema_sent_nullable: " + ",".join(report["sent_nullable"]))
    lines.append("schema_sent_enums: " + ",".join(report["sent_enums"]))
    return "\n".join(lines)


def semantic_rules() -> tuple[SemanticRule, ...]:
    """Custom validators. Identifier patterns that the schema already sends are noted in why."""

    return (
        SemanticRule(
            "ParameterScan",
            "_finite_bounds",
            "field",
            "Scan bounds, when present, must be finite numbers.",
            False,
            "JSON Schema type number does not reject NaN, infinity, or a boolean at the Python boundary.",
        ),
        SemanticRule(
            "ParameterScan",
            "_bounds_match_status",
            "model",
            "status=undefined requires lower and upper to be null. status=defined requires ordered finite bounds.",
            False,
            "The sent schema allows any combination of null and number on both bounds.",
        ),
        SemanticRule(
            "RequiredResolution",
            "_finite_value",
            "field",
            "A resolution value, when present, must be a finite number.",
            False,
            "JSON Schema type number does not reject NaN, infinity, or a boolean at the Python boundary.",
        ),
        SemanticRule(
            "RequiredResolution",
            "_value_matches_status",
            "model",
            "status=undefined requires value null. status=defined requires a numeric value.",
            False,
            "The sent schema allows a number with status undefined and null with status defined.",
        ),
        SemanticRule(
            "ExperimentPlan",
            "_strip_lists",
            "field",
            "Strip surrounding whitespace on control, confounder, procedure, stop, limitation, and safety strings.",
            False,
            "String normalization is not a JSON Schema keyword.",
        ),
        SemanticRule(
            "ExperimentPlan",
            "_lists_not_blank",
            "field",
            "Those list items must not be blank after stripping.",
            False,
            "The sent array items are plain strings with no minLength.",
        ),
        SemanticRule(
            "ExperimentPlan",
            "_plan_is_traceable",
            "model",
            "observable_ids are unique, required_resolution.observable_id is one of them, and safety_notes includes the exact sentence No autonomous physical execution.",
            False,
            "Uniqueness, the resolution cross-reference, and the exact safety sentence are absent from the sent schema. Identifier patterns on experiment_id and observable_ids are present.",
        ),
        SemanticRule(
            "ExperimentPlanResult",
            "_strip_blockers",
            "field",
            "Strip blocking-definition strings.",
            False,
            "String normalization is not a JSON Schema keyword.",
        ),
        SemanticRule(
            "ExperimentPlanResult",
            "_blockers_not_blank",
            "field",
            "Blocking-definition strings must not be blank.",
            False,
            "The sent array items are plain strings with no minLength.",
        ),
        SemanticRule(
            "ExperimentPlanResult",
            "_status_matches_plan",
            "model",
            "blocked requires experiment null and a blocker. ready requires a defined resolution and no blockers. partial requires an experiment whose resolution is undefined or whose blocker list is non-empty.",
            False,
            "The sent schema types experiment as object-or-null and status as an enum, without relating them to resolution.status.",
        ),
        SemanticRule(
            "ExperimentalCapability",
            "_finite",
            "field",
            "uncertainty must be a finite number greater than zero.",
            False,
            "exclusiveMinimum covers the lower bound. Finiteness is not in the sent schema. The observable_id pattern is.",
        ),
        SemanticRule(
            "FalsificationVerdict",
            "_finite_ratio",
            "field",
            "delta_over_sigma, when present, must be finite.",
            False,
            "The nullable number schema does not reject NaN or infinity.",
        ),
        SemanticRule(
            "FalsificationVerdict",
            "_refs_are_canonical",
            "field",
            "evidence_refs match the canonical id pattern and are unique.",
            False,
            "The sent evidence_refs items are plain strings. The pattern and uniqueness checks run only in Pydantic.",
        ),
        SemanticRule(
            "FalsificationVerdict",
            "_strip_limitations",
            "field",
            "Strip limitation strings.",
            False,
            "String normalization is not a JSON Schema keyword.",
        ),
        SemanticRule(
            "FalsificationVerdict",
            "_limitations_not_blank",
            "field",
            "Limitation strings must not be blank.",
            False,
            "The sent array items are plain strings with no minLength.",
        ),
        SemanticRule(
            "FalsificationVerdict",
            "_status_names_what_is_missing",
            "model",
            "NOT_YET_FALSIFIABLE requires required_next_definition. TESTABLE requires it to be null.",
            False,
            "The sent schema allows any combination of the status enum and the nullable string.",
        ),
    )


def domain_rules() -> tuple[SemanticRule, ...]:
    """Checks that run after a schema-valid object exists. None of them are sent to Meta."""

    return (
        SemanticRule(
            "design_experiment",
            "_guard",
            "domain",
            "target_claim_ids must exist on the parser result and observable_ids must exist on the observable design. A defined resolution or defined scan bound must be a number written in the hypothesis.",
            False,
            "JSON Schema cannot see the upstream parser, observable, or hypothesis text.",
        ),
        SemanticRule(
            "judge_hypothesis",
            "check_verdict",
            "domain",
            "evidence_refs must exist in the supplied state. TESTABLE requires a ready experiment, defined resolution, ready simulation, and a discriminating non-zero observable. BELOW_SENSITIVITY requires an explicit uncertainty above that resolution. NON_DISCRIMINATING is rejected when a selected observable still discriminates. NOT_YET_FALSIFIABLE may carry delta_over_sigma only when a ready simulation and a capability exist.",
            False,
            "These rules read the whole pipeline state. The verdict schema does not include that state.",
        ),
    )


def validator_index() -> set[tuple[str, str]]:
    """Return the custom validators declared on the experiment and verdict models."""

    found: set[tuple[str, str]] = set()
    for model in _VALIDATED_MODELS:
        decorators = model.__pydantic_decorators__
        for name in decorators.field_validators:
            found.add((model.__name__, name))
        for name in decorators.model_validators:
            found.add((model.__name__, name))
    return found


def render_pydantic_only_rules() -> str:
    """List validators the Meta schema does not enforce."""

    rules = [rule for rule in (*semantic_rules(), *domain_rules()) if not rule.in_json_schema]
    lines = [f"pydantic_only_rules: {len(rules)}"]
    for rule in rules:
        lines.append(f"{rule.model}.{rule.validator} [{rule.kind}]: {rule.rule}")
    return "\n".join(lines)


def _safe_value(value: object, secret: str) -> str:
    if value is None:
        rendered = "null"
    elif isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, (int, float)):
        rendered = str(value)
    elif isinstance(value, str):
        rendered = value
    else:
        try:
            rendered = json.dumps(value, default=str, ensure_ascii=False)
        except TypeError:
            return "omitted"
    rendered = redact_json_text(rendered, secret)
    if secret and secret in rendered:
        return "omitted"
    if len(rendered) > _VALUE_LIMIT:
        return rendered[:_VALUE_LIMIT] + "..."
    return rendered


def _array_counts(payload: dict[str, Any], experiment: object) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    blockers = payload.get("blocking_missing_definitions")
    counts["blocking_missing_definitions"] = len(blockers) if isinstance(blockers, list) else None
    names = (
        "controlled_variables",
        "control_groups",
        "confounders",
        "procedure_outline",
        "limitations",
        "parameter_scan",
        "independent_variables",
        "measured_variables",
        "safety_notes",
    )
    for name in names:
        value = experiment.get(name) if isinstance(experiment, dict) else None
        counts[name] = len(value) if isinstance(value, list) else None
    return counts


def redact_json_text(text: str, secret: str) -> str:
    """Remove a secret and bearer tokens without eating a closing JSON quote."""

    cleaned = text.replace(secret, "[redacted]") if secret else text
    return re.sub(r'Bearer\s+[^\s"\\]+', "Bearer [redacted]", cleaned)


def _write_redacted(path: Path, document: dict[str, Any], secret: str) -> None:
    text = json.dumps(document, indent=2, ensure_ascii=False)
    cleaned = redact_json_text(text, secret)
    if secret and secret in cleaned:
        raise RuntimeError("refusing to write a diagnostic that still contains the API key")
    if re.search(r"Bearer\s+(?!\[redacted\])\S+", cleaned):
        raise RuntimeError("refusing to write a diagnostic that still contains an authorization token")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cleaned + "\n", encoding="utf-8")


def _patterns(schema: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
            return
        if not isinstance(node, dict):
            return
        pattern = node.get("pattern")
        if isinstance(pattern, str):
            found.append(f"{path}={pattern}")
        for key, value in node.items():
            if key == "pattern":
                continue
            walk(value, f"{path}.{key}" if path else key)

    walk(schema, "")
    return found


def _nullable_fields(schema: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
            return
        if not isinstance(node, dict):
            return
        options = node.get("anyOf")
        if isinstance(options, list) and any(
            isinstance(option, dict) and option.get("type") == "null" for option in options
        ):
            found.append(path or "$")
        properties = node.get("properties")
        if isinstance(properties, dict):
            for key, value in properties.items():
                walk(value, f"{path}.{key}" if path else key)
        if "items" in node:
            walk(node["items"], f"{path}[]")
        for key in ("anyOf", "oneOf", "allOf"):
            if isinstance(node.get(key), list):
                for index, item in enumerate(node[key]):
                    walk(item, f"{path}.{key}[{index}]")

    walk(schema, "")
    return found


def _enum_fields(schema: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, path)
            return
        if not isinstance(node, dict):
            return
        enum = node.get("enum")
        if isinstance(enum, list) and path:
            found.append(f"{path}={'|'.join(str(item) for item in enum)}")
        properties = node.get("properties")
        if isinstance(properties, dict):
            for key, value in properties.items():
                walk(value, f"{path}.{key}" if path else key)
        if "items" in node:
            walk(node["items"], f"{path}[]")
        for key in ("anyOf", "oneOf", "allOf"):
            if isinstance(node.get(key), list):
                for item in node[key]:
                    walk(item, path)

    walk(schema, "")
    return found
