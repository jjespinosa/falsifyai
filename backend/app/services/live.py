"""Shared live-call path. It does not catch errors and switch to the stub."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.providers.meta import MetaModelProvider, ProviderResponseError
from app.providers.schema_json import strict_json_schema
from app.providers.transport import ModelTransport, UrllibTransport


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
    try:
        payload = json.loads(completion.content)
    except json.JSONDecodeError:
        raise ProviderResponseError(
            "The live model response did not match the required schema."
        ) from None
    try:
        return model.model_validate(payload)
    except ValidationError:
        raise ProviderResponseError(
            "The live model response did not match the required schema."
        ) from None
