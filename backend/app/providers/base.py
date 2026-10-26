"""Provider interface for text completion.

Completions are data. Callers must not execute text returned by a provider.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class ModelCompletion(BaseModel):
    """Text returned by a model provider."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    content: str
    stub: bool


class ModelProvider(Protocol):
    """Minimal completion interface shared by the Meta client and test doubles."""

    model_id: str

    def complete(self, *, system: str, user: str) -> ModelCompletion:
        """Return a completion for a system instruction and a user message."""
