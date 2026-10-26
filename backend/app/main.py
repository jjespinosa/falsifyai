"""FalsifyAI HTTP shell for milestone M0."""

from fastapi import FastAPI

from app import __version__
from app.config import Settings, load_settings
from app.providers.base import ModelProvider
from app.providers.stub import StubModelProvider
from app.schemas.health import HealthResponse


def create_app(
    settings: Settings | None = None,
    *,
    provider: ModelProvider | None = None,
) -> FastAPI:
    """Build the application.

    The default provider is the in-memory stub. M0 exposes no model route.
    """

    resolved = load_settings() if settings is None else settings
    app = FastAPI(title="FalsifyAI", version=__version__)
    app.state.settings = resolved
    app.state.provider = (
        provider
        if provider is not None
        else StubModelProvider(model_id=resolved.meta_model_id)
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="falsifyai", milestone="M0")

    return app


app = create_app()
