"""JSON Schema for Meta structured output.

Pydantic emits ``$ref`` nodes. The Meta schema decoder rejects recursive
references, so this helper inlines local definitions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a non-recursive object schema with every property required."""

    raw = model.model_json_schema()
    definitions = raw.get("$defs", {})
    return _inline(raw, definitions, stack=())


def _inline(node: Any, definitions: dict[str, Any], *, stack: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_inline(item, definitions, stack=stack) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = str(node["$ref"]).rsplit("/", 1)[-1]
        if name in stack:
            raise ValueError(f"recursive schema is not supported: {name}")
        target = definitions.get(name)
        if not isinstance(target, dict):
            raise ValueError(f"missing schema definition: {name}")
        inlined = _inline(target, definitions, stack=(*stack, name))
        extras = {
            key: _inline(value, definitions, stack=stack)
            for key, value in node.items()
            if key != "$ref"
        }
        if isinstance(inlined, dict):
            return _lock({**inlined, **extras})
        return extras
    copied = {
        key: _inline(value, definitions, stack=stack)
        for key, value in node.items()
        if key != "$defs"
    }
    return _lock(copied)


def strict_subset_issues(schema: dict[str, Any]) -> list[str]:
    """Return reasons a schema would fail Meta's strict subset.

    The domain model is not changed here. Callers use this to decide whether
    ``strict: true`` is honest for the schema they already send.
    """

    issues: list[str] = []
    if schema.get("type") != "object":
        issues.append("root is not an object")
    for forbidden in ("anyOf", "oneOf", "allOf", "enum", "not"):
        if forbidden in schema:
            issues.append(f"root uses {forbidden}")
    _check_nodes(schema, issues)
    if _schema_depth(schema) > 10:
        issues.append("nesting depth exceeds 10")
    return issues


def _check_nodes(node: Any, issues: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _check_nodes(item, issues)
        return
    if not isinstance(node, dict):
        return
    if "$ref" in node:
        issues.append("schema still contains a local reference")
    for forbidden in ("oneOf", "allOf"):
        if forbidden in node:
            issues.append(f"{forbidden} is not allowed in strict mode")
    properties = node.get("properties")
    if node.get("type") == "object" and isinstance(properties, dict):
        if node.get("additionalProperties") is not False:
            issues.append("an object does not set additionalProperties to false")
        required = node.get("required")
        if not isinstance(required, list) or set(required) != set(properties):
            issues.append("an object does not require every property")
    for value in node.values():
        _check_nodes(value, issues)


def _schema_depth(node: Any, depth: int = 1) -> int:
    if not isinstance(node, dict):
        return depth
    depths = [depth]
    properties = node.get("properties")
    if isinstance(properties, dict):
        depths.extend(_schema_depth(value, depth + 1) for value in properties.values())
    if "items" in node:
        depths.append(_schema_depth(node["items"], depth + 1))
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(node.get(key), list):
            depths.extend(_schema_depth(item, depth + 1) for item in node[key])
    return max(depths)


def _lock(node: dict[str, Any]) -> dict[str, Any]:
    if node.get("type") == "object" and isinstance(node.get("properties"), dict):
        node["additionalProperties"] = False
        node["required"] = list(node["properties"])
    return node
