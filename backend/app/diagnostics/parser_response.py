"""Sanitized diagnostics for a ParserResult that failed validation.

These helpers do not call the network and do not include request headers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.providers.schema_json import strict_json_schema
from app.schemas.claim import ClaimProvenance, ScientificClaim
from app.schemas.identifiers import ASSUMPTION_ID_PATTERN, CLAIM_ID_PATTERN
from app.schemas.parser import (
    ClaimVariable,
    ExtractedAssumption,
    MissingDefinition,
    ParsedClaim,
    ParserResult,
    UndefinedTerm,
)

_VALUE_LIMIT = 240
_VALIDATED_MODELS: tuple[type[BaseModel], ...] = (
    ParserResult,
    ParsedClaim,
    MissingDefinition,
    ClaimVariable,
    ExtractedAssumption,
    UndefinedTerm,
    ScientificClaim,
    ClaimProvenance,
)


@dataclass(frozen=True)
class SemanticRule:
    """One custom validator and whether Meta's JSON Schema can enforce it."""

    model: str
    validator: str
    kind: str
    rule: str
    in_json_schema: bool
    why: str


def describe_validation_error(exc: ValidationError, *, secret: str = "") -> list[dict[str, str]]:
    """Return every ParserResult error, including a redacted value when that is safe."""

    rows: list[dict[str, str]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        path = ".".join(str(part) for part in location)
        rows.append(
            {
                "path": redact_json_text(path, secret),
                "type": str(error.get("type", "")),
                "message": redact_json_text(str(error.get("msg", "")), secret),
                "field": str(location[-1]) if location else "",
                "value_type": type(error.get("input")).__name__,
                "value": _safe_value(error.get("input"), secret),
            }
        )
    return rows


def render_validation_diagnostic(exc: ValidationError, *, secret: str = "") -> str:
    """Format every parser validation error. The value is redacted first."""

    rows = describe_validation_error(exc, secret=secret)
    lines = [f"validation_error_count: {len(rows)}"]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. path={row['path']} type={row['type']} "
            f"field={row['field']} value_type={row['value_type']} "
            f"value={row['value']} message={row['message']}"
        )
    return "\n".join(lines)


def completion_facts(body: object, *, http_status: int | None) -> dict[str, Any]:
    """Read status, model, finish reason, and token counts from a response body."""

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
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def redact(text: str, secret: str) -> str:
    """Remove a known secret and any bearer token from diagnostic text."""

    cleaned = text.replace(secret, "[redacted]") if secret else text
    return re.sub(r"Bearer\s+\S+", "Bearer [redacted]", cleaned)


def redact_json_text(text: str, secret: str) -> str:
    """Remove a secret and bearer tokens without eating a closing JSON quote."""

    cleaned = text.replace(secret, "[redacted]") if secret else text
    return re.sub(r'Bearer\s+[^\s"\\]+', "Bearer [redacted]", cleaned)


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


def write_structured_response(path: Path, raw_content: str, *, secret: str) -> None:
    """Save the model message. Refuse if the secret would still be on disk."""

    text = redact(raw_content, secret)
    if secret and secret in text:
        raise RuntimeError("refusing to write a response that still contains the API key")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def content_profile(payload: object, raw_text: str) -> dict[str, Any]:
    """Summarize array sizes and the longest strings in a parser payload."""

    arrays: dict[str, int] = {}
    strings: list[dict[str, Any]] = []
    _walk(payload, "$", arrays, strings)
    strings.sort(key=lambda item: item["length"], reverse=True)
    top_level = sorted(payload) if isinstance(payload, dict) else []

    def _count(name: str) -> int | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get(name)
        if isinstance(value, list):
            return len(value)
        return None

    return {
        "character_count": len(raw_text),
        "top_level_keys": top_level,
        "claims": _count("claims"),
        "assumptions": _count("assumptions"),
        "undefined_terms": _count("undefined_terms"),
        "parser_notes": _count("parser_notes"),
        "array_lengths": arrays,
        "longest_strings": strings[:8],
    }


def compare_parser_schemas() -> dict[str, Any]:
    """Compare the Pydantic schema, the inlined schema, and the schema sent to Meta.

    The production provider sends the transformed schema unchanged.
    """

    raw = ParserResult.model_json_schema()
    transformed = strict_json_schema(ParserResult)
    sent = transformed
    return {
        "sent_equals_transformed": sent == transformed,
        "raw_ref_count": json.dumps(raw).count('"$ref"'),
        "transformed_ref_count": json.dumps(transformed).count('"$ref"'),
        "differences": _schema_differences(raw, transformed),
    }


def semantic_rules() -> tuple[SemanticRule, ...]:
    """Custom validators that JSON Schema does not enforce."""

    provenance = (
        "Cross-field provenance: a numeric value requires a unit; only a simulated "
        "claim may name spec_id or routine_id; a measured claim requires an observable; "
        "a literature-derived claim requires source_ref; a simulated claim requires both "
        "ids and cannot carry source_ref."
    )
    established = (
        "Established epistemic status requires measured or literature-derived provenance. "
        "Epistemic status does not decide operationality."
    )
    return (
        SemanticRule("ClaimVariable", "_strip", "field", "Strip surrounding whitespace.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("ClaimVariable", "_unit_not_blank", "field", "A unit, when present, must not be blank.", False, "The nullable unit schema allows an empty string."),
        SemanticRule("MissingDefinition", "_strip", "field", "Strip the missing-definition statement.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("ParsedClaim", "_strip_identity", "field", "Strip claim_id and statement.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("ParsedClaim", "_strip_items", "field", "Strip assumption items.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("ParsedClaim", "_items_not_blank", "field", "Assumption items must not be blank.", False, "Those array items have no minLength."),
        SemanticRule("ParsedClaim", "_operational_means_defined", "model", "A critical missing definition, a genuinely undefined variable, or a missing quantity makes a claim non-operational. A missing number, range, or tolerance does not set defined to false. " + established, False, "JSON Schema does not express this cross-field rule."),
        SemanticRule("ExtractedAssumption", "_strip", "field", "Strip assumption_id and statement.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("UndefinedTerm", "_strip", "field", "Strip term and reason.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("ParserResult", "_identifiers_resolve", "model", "Claim ids and assumption ids are unique, and every reference points at an extracted claim.", False, "JSON Schema does not enforce uniqueness or references between arrays."),
        SemanticRule("ScientificClaim", "_strip_text_fields", "field", "Strip text provenance fields.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("ScientificClaim", "_reject_blank", "field", "Observable, source, and unit must not be blank when present.", False, "Those nullable strings allow an empty string."),
        SemanticRule("ScientificClaim", "_numeric_value", "field", "value must be a finite number, not a string or boolean.", False, "JSON Schema type number still accepts values this check rejects, including booleans at the Python boundary."),
        SemanticRule("ScientificClaim", "_finite_value", "field", "value must be finite.", False, "JSON Schema does not reject NaN or infinity once a number is accepted."),
        SemanticRule("ScientificClaim", "_check_provenance", "model", provenance + " " + established, False, "The sent schema lists the fields but does not relate them."),
        SemanticRule("ClaimProvenance", "_strip_text_fields", "field", "Strip text provenance fields.", False, "String normalization is not a JSON Schema keyword."),
        SemanticRule("ClaimProvenance", "_reject_blank", "field", "Observable, source, and unit must not be blank when present.", False, "Those nullable strings allow an empty string."),
        SemanticRule("ClaimProvenance", "_numeric_value", "field", "value must be a finite number, not a string or boolean.", False, "JSON Schema type number still accepts values this check rejects, including booleans at the Python boundary."),
        SemanticRule("ClaimProvenance", "_finite_value", "field", "value must be finite.", False, "JSON Schema does not reject NaN or infinity once a number is accepted."),
        SemanticRule("ClaimProvenance", "_check_provenance", "model", provenance, False, "The sent schema lists the fields but does not relate them."),
    )


def grounding_rules() -> tuple[SemanticRule, ...]:
    """Checks applied after ParserResult accepts the payload. The schema cannot see the user text."""

    return (
        SemanticRule(
            "ensure_stated_evidence",
            "stated_number_and_source",
            "post",
            "A numeric provenance value and a source_ref must appear in the user hypothesis.",
            False,
            "JSON Schema cannot compare the payload with the original hypothesis text.",
        ),
    )


def parser_contract_audit() -> dict[str, Any]:
    """Compare the sent ParserResult schema with the rules that remain after generation."""

    sent = strict_json_schema(ParserResult)
    return {
        "claim_id_pattern_sent": _pattern_present(sent, CLAIM_ID_PATTERN),
        "assumption_id_pattern_sent": _pattern_present(sent, ASSUMPTION_ID_PATTERN),
        "sent_equals_transformed": sent == strict_json_schema(ParserResult),
        "absent": [
            "blank-string rejection",
            "finite numeric values",
            "unique ids",
            "provenance cross-field rules",
            "epistemic/operational rules",
            "critical missing definitions",
            "evidence grounding against user input",
        ],
        "absent_validators": [
            f"{rule.model}.{rule.validator}"
            for rule in (*semantic_rules(), *grounding_rules())
            if not rule.in_json_schema
        ],
    }


def write_parser_failure(
    path: Path,
    *,
    content: str,
    metadata: dict[str, Any],
    validation_error: ValidationError | None,
    secret: str,
) -> None:
    """Save the structured parser message and safe metadata. Headers are not accepted."""

    try:
        parsed: object = json.loads(content)
    except json.JSONDecodeError:
        parsed = content
    profile = content_profile(parsed, content) if isinstance(parsed, dict) else {
        "character_count": len(content),
        "top_level_keys": [],
    }
    document: dict[str, Any] = {
        "metadata": {
            "http_status": metadata.get("http_status"),
            "finish_reason": metadata.get("finish_reason"),
            "model": metadata.get("model"),
            "prompt_tokens": metadata.get("prompt_tokens"),
            "completion_tokens": metadata.get("completion_tokens"),
            "reasoning_tokens": metadata.get("reasoning_tokens"),
            "total_tokens": metadata.get("total_tokens"),
            "character_count": profile["character_count"],
            "top_level_keys": profile["top_level_keys"],
        },
        "content": parsed,
    }
    if validation_error is not None:
        document["validation_errors"] = describe_validation_error(validation_error, secret=secret)
    text = redact_json_text(json.dumps(document, indent=2, ensure_ascii=False), secret)
    if secret and secret in text:
        raise RuntimeError("refusing to write a parser response that still contains the API key")
    if re.search(r"Bearer\s+(?!\[redacted\])\S+", text):
        raise RuntimeError("refusing to write a parser response that still contains an authorization token")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def validator_index() -> set[tuple[str, str]]:
    """Return the custom validators declared on the scientific models."""

    found: set[tuple[str, str]] = set()
    for model in _VALIDATED_MODELS:
        decorators = model.__pydantic_decorators__
        for name in decorators.field_validators:
            found.add((model.__name__, name))
        for name in decorators.model_validators:
            found.add((model.__name__, name))
    return found


def _pattern_present(node: Any, pattern: str) -> bool:
    if isinstance(node, dict):
        if node.get("pattern") == pattern:
            return True
        return any(_pattern_present(value, pattern) for value in node.values())
    if isinstance(node, list):
        return any(_pattern_present(item, pattern) for item in node)
    return False


def _walk(
    node: object,
    path: str,
    arrays: dict[str, int],
    strings: list[dict[str, Any]],
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, f"{path}.{key}", arrays, strings)
        return
    if isinstance(node, list):
        arrays[path] = len(node)
        for index, value in enumerate(node):
            _walk(value, f"{path}[{index}]", arrays, strings)
        return
    if isinstance(node, str):
        strings.append({"path": path, "length": len(node)})


def _schema_differences(raw: dict[str, Any], transformed: dict[str, Any]) -> list[str]:
    raw_objects = _objects_by_title(raw)
    transformed_objects = _objects_by_title(transformed)
    differences: list[str] = []
    if '"$ref"' in json.dumps(raw) and '"$ref"' not in json.dumps(transformed):
        differences.append("$ref nodes in the Pydantic schema are inlined before the request.")
    if "$defs" in raw and "$defs" not in transformed:
        differences.append("$defs is removed after inlining.")
    for name in sorted(set(raw_objects) & set(transformed_objects)):
        left = raw_objects[name]
        right = transformed_objects[name]
        if left["properties"] != right["properties"]:
            differences.append(
                f"{name} properties differ: pydantic={left['properties']} sent={right['properties']}"
            )
        if left["required"] != right["required"]:
            added = sorted(set(right["required"]) - set(left["required"]))
            differences.append(
                f"{name} required differs: pydantic={left['required']} sent={right['required']} "
                f"added={added}"
            )
        if left["additionalProperties"] != right["additionalProperties"]:
            differences.append(
                f"{name} additionalProperties differs: "
                f"pydantic={left['additionalProperties']} sent={right['additionalProperties']}"
            )
        if left["defaults"] != right["defaults"]:
            differences.append(
                f"{name} defaults differ: pydantic={left['defaults']} sent={right['defaults']}"
            )
        if left["enums"] != right["enums"]:
            differences.append(
                f"{name} enums differ: pydantic={left['enums']} sent={right['enums']}"
            )
        if left["nullable"] != right["nullable"]:
            differences.append(
                f"{name} nullable fields differ: pydantic={left['nullable']} sent={right['nullable']}"
            )
        if left["array_items"] != right["array_items"]:
            differences.append(
                f"{name} array item schemas differ: "
                f"pydantic={left['array_items']} sent={right['array_items']}"
            )
        if left["anyOf"] != right["anyOf"]:
            differences.append(
                f"{name} anyOf fields differ: pydantic={left['anyOf']} sent={right['anyOf']}"
            )
    return differences


def _objects_by_title(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = schema.get("$defs", {})
    found: dict[str, dict[str, Any]] = {}

    def resolve(node: Any) -> Any:
        if isinstance(node, dict) and "$ref" in node and isinstance(definitions, dict):
            name = str(node["$ref"]).rsplit("/", 1)[-1]
            target = definitions.get(name)
            if isinstance(target, dict):
                return target
        return node

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        title = node.get("title")
        if node.get("type") == "object" and isinstance(properties, dict) and isinstance(title, str):
            resolved = {
                key: resolve(value) if isinstance(value, dict) else value
                for key, value in properties.items()
            }
            found[title] = {
                "properties": sorted(resolved),
                "required": sorted(node.get("required") or []),
                "additionalProperties": node.get("additionalProperties", "absent"),
                "defaults": sorted(
                    key
                    for key, value in resolved.items()
                    if isinstance(value, dict) and "default" in value
                ),
                "enums": sorted(
                    key
                    for key, value in resolved.items()
                    if isinstance(value, dict) and "enum" in _resolved_schema(value, definitions)
                ),
                "nullable": sorted(
                    key
                    for key, value in resolved.items()
                    if isinstance(value, dict) and _is_nullable(value, definitions)
                ),
                "array_items": sorted(
                    key for key, value in resolved.items() if isinstance(value, dict) and "items" in value
                ),
                "anyOf": sorted(
                    key
                    for key, value in resolved.items()
                    if isinstance(value, dict) and "anyOf" in _resolved_schema(value, definitions)
                ),
            }
        for value in node.values():
            walk(value)

    walk(schema)
    return found


def _resolved_schema(node: dict[str, Any], definitions: object) -> dict[str, Any]:
    if "$ref" not in node or not isinstance(definitions, dict):
        return node
    name = str(node["$ref"]).rsplit("/", 1)[-1]
    target = definitions.get(name)
    if isinstance(target, dict):
        return target
    return node


def _is_nullable(node: dict[str, Any], definitions: object) -> bool:
    resolved = _resolved_schema(node, definitions)
    options = resolved.get("anyOf")
    if not isinstance(options, list):
        return False
    return any(
        isinstance(option, dict) and _resolved_schema(option, definitions).get("type") == "null"
        for option in options
    )
