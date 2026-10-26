"""In-memory Meta provider double for tests and the default stub mode."""

from app.providers.base import ModelCompletion


class StubModelProvider:
    """Returns scripted text and records prompts. It performs no network I/O."""

    def __init__(self, *, model_id: str, content: str = "") -> None:
        self.model_id = model_id
        self._content = content
        self.prompts: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> ModelCompletion:
        if user.strip() == "":
            raise ValueError("user prompt must not be empty")
        self.prompts.append((system, user))
        return ModelCompletion(model_id=self.model_id, content=self._content, stub=True)

    def __repr__(self) -> str:
        return f"StubModelProvider(model_id={self.model_id!r})"
