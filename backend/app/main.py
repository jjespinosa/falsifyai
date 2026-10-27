"""FalsifyAI HTTP shell for milestone M6."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.analyze import router as analyze_router
from app.api.run import router as run_router
from app.api.simulate import router as simulate_router
from app.config import Settings, load_settings
from app.help import help_document
from app.providers.base import ModelProvider
from app.providers.stub import StubModelProvider
from app.providers.transport import ModelTransport
from app.schemas.health import HealthResponse
from app.schemas.help import HelpResponse


def create_app(
    settings: Settings | None = None,
    *,
    provider: ModelProvider | None = None,
    live_transport: ModelTransport | None = None,
) -> FastAPI:
    """Build the application.

    The default provider is the in-memory stub. M0 exposes no model route.
    """

    resolved = load_settings() if settings is None else settings
    app = FastAPI(
        title="FalsifyAI",
        version=__version__,
        summary="Adversarial scientific instrument through one falsification run.",
        description=(
            "FalsifyAI looks for an experiment that could falsify a hypothesis. "
            "POST /api/v1/run executes the verified pipeline once. "
            "Analysis routes and the run default to stub mode and do not call the network. "
            "POST /api/v1/simulate executes a declarative spec locally and does not "
            "call the model. Live mode is explicit and does not fall back to the stub. "
            "See GET /help and docs/m5.md."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_CORS_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = resolved
    app.state.live_transport = live_transport
    app.state.provider = (
        provider
        if provider is not None
        else StubModelProvider(model_id=resolved.meta_model_id)
    )

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["shell"],
        summary="Process health",
    )
    def health() -> HealthResponse:
        """Report that the M6 shell is running.

        The body names the service and milestone. It does not include configuration.
        """

        return HealthResponse(status="ok", service="falsifyai", milestone="M6")

    @app.get(
        "/help",
        response_model=HelpResponse,
        tags=["shell"],
        summary="Milestone help",
    )
    def help_route() -> HelpResponse:
        """Describe the M6 contract.

        The document is static. It does not read or return environment values.
        """

        return help_document()

    app.include_router(analyze_router)
    app.include_router(simulate_router)
    app.include_router(run_router)
    return app


DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


app = create_app()
