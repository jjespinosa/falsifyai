"""FalsifyAI HTTP shell for milestone M7."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.analyze import router as analyze_router
from app.api.run import router as run_router
from app.api.simulate import router as simulate_router
from app.config import Settings, load_settings
from app.meta_diagnostics import log_meta_runtime_diagnostics
from app.demo_guard import BoundedBodyMiddleware, LiveQuota
from app.help import help_document
from app.providers.base import ModelProvider
from app.providers.stub import StubModelProvider
from app.providers.transport import ModelTransport
from app.schemas.health import HealthResponse
from app.schemas.help import HelpResponse
from app.static_ui import mount_spa


def create_app(
    settings: Settings | None = None,
    *,
    provider: ModelProvider | None = None,
    live_transport: ModelTransport | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    """Build the application.

    The default provider is the in-memory stub. A built frontend is served only
    when static_dir or FALSIFY_STATIC_DIR points at frontend/dist.
    """

    resolved = load_settings() if settings is None else settings
    if resolved.meta_runtime_diagnostics:
        _log_runtime_diagnostics(resolved, from_process=settings is None)
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
            "See GET /help and docs/RELEASE_M7.md."
        ),
    )
    app.add_middleware(BoundedBodyMiddleware, max_bytes=resolved.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_CORS_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = resolved
    app.state.live_quota = LiveQuota(resolved.live_run_limit, resolved.live_run_window_seconds)
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
        """Report that the M7 shell is running.

        The body names the service and milestone. It does not include configuration.
        """

        return HealthResponse(status="ok", service="falsifyai", milestone="M7")

    @app.get(
        "/help",
        response_model=HelpResponse,
        tags=["shell"],
        summary="Milestone help",
    )
    def help_route() -> HelpResponse:
        """Describe the M7 contract.

        The document is static. It does not read or return environment values.
        """

        return help_document()

    app.include_router(analyze_router)
    app.include_router(simulate_router)
    app.include_router(run_router)
    mount_spa(app, _static_directory(static_dir))
    return app


def _log_runtime_diagnostics(resolved: Settings, *, from_process: bool) -> None:
    """Read the raw process values when the app is loading its own environment."""

    if from_process:
        api_key = os.environ.get("MODEL_API_KEY", "")
        meta_base_url = os.environ.get("META_BASE_URL", resolved.meta_base_url)
        meta_model_id = os.environ.get("META_MODEL_ID", "")
    else:
        api_key = resolved.model_api_key.get_secret_value()
        meta_base_url = resolved.meta_base_url
        meta_model_id = resolved.meta_model_id
    log_meta_runtime_diagnostics(
        api_key=api_key,
        meta_base_url=meta_base_url,
        meta_model_id=meta_model_id,
    )


def _static_directory(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    raw = os.environ.get("FALSIFY_STATIC_DIR", "").strip()
    if raw == "":
        return None
    return Path(raw)


DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


app = create_app()
