"""Shared live-call path. It does not catch errors and switch to the stub."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.diagnostics.parser_response import completion_facts
from app.providers.meta import MetaModelProvider, ProviderResponseError
from app.providers.schema_json import strict_json_schema
from app.providers.transport import ModelTransport, UrllibTransport


@dataclass(frozen=True)
class StructuredCallFailure:
    """Safe attachment for one rejected structured completion. It is not part of str()."""

    failure_kind: str
    content: str
    validation_error: ValidationError | None
    metadata: dict[str, Any]


def complete_structured(
    settings: Settings,
    transport: ModelTransport | None,
    *,
    system: str,
    user: str,
    schema_name: str,
    model: type[BaseModel],
    reasoning_effort: str,
) -> Any:
    """Call Muse Spark and parse the message with the Pydantic model."""

    provider = MetaModelProvider(settings, transport=transport or UrllibTransport())
    completion = provider.complete(
        system=system,
        user=user,
        response_schema=strict_json_schema(model),
        schema_name=schema_name,
        reasoning_effort=reasoning_effort,
    )
    metadata = _call_metadata(transport)
    try:
        payload = json.loads(completion.content)
    except json.JSONDecodeError:
        raise ProviderResponseError(
            "The live model response did not match the required schema.",
            diagnostic=StructuredCallFailure(
                "json_decode",
                completion.content,
                None,
                metadata,
            ),
        ) from None
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ProviderResponseError(
            "The live model response did not match the required schema.",
            diagnostic=StructuredCallFailure(
                "schema_validation",
                completion.content,
                exc,
                metadata,
            ),
        ) from None


def _call_metadata(transport: ModelTransport | None) -> dict[str, Any]:
    body = getattr(transport, "last_body", None) if transport is not None else None
    facts = completion_facts(body, http_status=getattr(transport, "last_http_status", None))
    usage = getattr(transport, "last_usage", None) if transport is not None else None
    if facts.get("reasoning_tokens") is None and isinstance(usage, dict):
        reasoning = usage.get("reasoning_tokens")
        if isinstance(reasoning, int):
            facts["reasoning_tokens"] = reasoning
    return facts
