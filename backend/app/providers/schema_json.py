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


def _lock(node: dict[str, Any]) -> dict[str, Any]:
    if node.get("type") == "object" and isinstance(node.get("properties"), dict):
        node["additionalProperties"] = False
        node["required"] = list(node["properties"])
    return node
