"""Static help for milestone M0.

This module does not read settings and does not include secret values.
"""

from app.schemas.help import HelpContract, HelpEndpoint, HelpLink, HelpResponse, HelpVariable

_SUMMARY = (
    "FalsifyAI looks for an experiment that could falsify a hypothesis. "
    "The parser extracts the smallest set of claims. The critic looks for what "
    "blocks an experimental test. Both default to stub mode. Live mode is explicit "
    "and does not fall back to the stub. Later pipeline stages are not implemented."
)


def help_document() -> HelpResponse:
    """Return the M0 help document."""

    return HelpResponse(
        service="falsifyai",
        milestone="M1",
        summary=_SUMMARY,
        documentation=[
            HelpLink(kind="guide", location="docs/m1.md"),
            HelpLink(kind="guide", location="docs/m0.md"),
            HelpLink(kind="openapi", location="/docs"),
            HelpLink(kind="redoc", location="/redoc"),
        ],
        endpoints=[
            HelpEndpoint(
                method="GET",
                path="/health",
                summary="Report that the shell is running. The body does not include configuration.",
            ),
            HelpEndpoint(
                method="GET",
                path="/help",
                summary="Return this document. It describes the contract, not the live environment.",
            ),
            HelpEndpoint(
                method="GET",
                path="/docs",
                summary="Open the interactive OpenAPI reference.",
            ),
            HelpEndpoint(
                method="GET",
                path="/redoc",
                summary="Open the ReDoc reference.",
            ),
            HelpEndpoint(
                method="POST",
                path="/api/v1/analyze/parse",
                summary="Extract claims from a hypothesis. The default mode is stub.",
            ),
            HelpEndpoint(
                method="POST",
                path="/api/v1/analyze/critique",
                summary="Critique a hypothesis together with a parser result. The default mode is stub.",
            ),
        ],
        configuration=[
            HelpVariable(
                name="MODEL_API_KEY",
                required_for="live Meta Model API calls only",
                notes=(
                    "Read from the process environment. The M0 shell starts without it. "
                    "Tests do not send it over the network. Never commit the value."
                ),
            ),
            HelpVariable(
                name="META_BASE_URL",
                required_for="live Meta Model API calls",
                notes=(
                    "Must be an absolute https URL. When the variable is absent, "
                    "the shell uses https://api.meta.ai/v1."
                ),
            ),
            HelpVariable(
                name="META_MODEL_ID",
                required_for="live Meta Model API calls",
                notes=(
                    "Set it explicitly. muse-spark-1.3 is the verified primary model. "
                    "An empty value does not select a model."
                ),
            ),
        ],
        contracts=[
            HelpContract(
                name="HypothesisInput",
                summary=(
                    "A user hypothesis: statement is required; domain, context, and assumptions "
                    "are optional. It is not evidence and it cannot carry a verdict."
                ),
            ),
            HelpContract(
                name="ScientificClaim",
                summary=(
                    "One claim labeled measured, literature-derived, assumed, simulated, or speculative. "
                    "A measured claim names an observable. A number includes a unit. "
                    "A literature-derived claim names source_ref. A simulated claim names "
                    "spec_id and routine_id. There is no field for executable code."
                ),
            ),
        ],
        not_available=[
            "Null Model",
            "Observable Designer",
            "Simulator",
            "Experiment Designer",
            "Falsification Judge",
            "frontend",
            "database",
            "DQ-12 demo",
            "Duffing demo",
        ],
    )
