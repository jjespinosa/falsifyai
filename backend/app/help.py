"""Static help for milestone M4.

This module does not read settings and does not include secret values.
"""

from app.schemas.help import HelpContract, HelpEndpoint, HelpLink, HelpResponse, HelpVariable

_SUMMARY = (
    "FalsifyAI looks for an experiment that could falsify a hypothesis. "
    "Milestone M4 extracts claims, critiques them, builds a competing null model, "
    "proposes observables, plans a numerical comparison only when both models are "
    "quantitative, designs a controlled experiment, and assigns one falsification "
    "status. POST /api/v1/simulate runs a registered family locally and does not "
    "call the model. Analysis routes default to stub mode. Live mode is explicit "
    "and does not fall back to the stub."
)


def help_document() -> HelpResponse:
    """Return the M4 help document."""

    return HelpResponse(
        service="falsifyai",
        milestone="M4",
        summary=_SUMMARY,
        documentation=[
            HelpLink(kind="guide", location="docs/m4.md"),
            HelpLink(kind="guide", location="docs/m3.md"),
            HelpLink(kind="guide", location="docs/m2.md"),
            HelpLink(kind="guide", location="docs/m1.md"),
            HelpLink(kind="guide", location="docs/m0.md"),
            HelpLink(kind="openapi", location="/docs"),
            HelpLink(kind="redoc", location="/redoc"),
        ],
        endpoints=[
            HelpEndpoint(
                method="GET",
                path="/health",
                summary="Report that the M4 shell is running. The body does not include configuration.",
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
            HelpEndpoint(
                method="POST",
                path="/api/v1/analyze/null-model",
                summary="Build a competing null model. The default mode is stub.",
            ),
            HelpEndpoint(
                method="POST",
                path="/api/v1/analyze/observable",
                summary="Propose observables that might separate H1 from H0. The default mode is stub.",
            ),
            HelpEndpoint(
                method="POST",
                path="/api/v1/analyze/simulation-plan",
                summary="Decide whether H0 and H1 can be computed. The default mode is stub.",
            ),
            HelpEndpoint(
                method="POST",
                path="/api/v1/simulate",
                summary="Evaluate a declarative spec locally. This route does not call the model.",
            ),
            HelpEndpoint(
                method="POST",
                path="/api/v1/analyze/experiment",
                summary="Design a controlled comparison. The default mode is stub.",
            ),
            HelpEndpoint(
                method="POST",
                path="/api/v1/analyze/judge",
                summary="Assign one falsification status. The default mode is stub.",
            ),
        ],
        configuration=[
            HelpVariable(
                name="MODEL_API_KEY",
                required_for="live Meta Model API calls only",
                notes=(
                    "Read from the process environment. The service starts without it. "
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
                name="NullModelResult",
                summary=(
                    "One or more competing explanations. model_id is lowercase h0. "
                    "It can say that H0 mimics the claim. It does not issue a verdict."
                ),
            ),
            HelpContract(
                name="ObservableDesignResult",
                summary=(
                    "Candidate measurements. An empty list is valid when definitions are missing. "
                    "A discriminating flag is not support for the hypothesis and not a verdict."
                ),
            ),
            HelpContract(
                name="SimulationPlanResult",
                summary=(
                    "ready includes a declarative spec. blocked leaves the spec empty and names "
                    "the missing quantitative definition. A blocked plan is a valid scientific result."
                ),
            ),
            HelpContract(
                name="SimulationResult",
                summary=(
                    "Curves for H0, H1, and their difference. The difference is a model prediction only."
                ),
            ),
            HelpContract(
                name="ExperimentPlanResult",
                summary=(
                    "ready, partial, or blocked. Partial describes a meaningful comparison "
                    "whose decisive resolution is still undefined."
                ),
            ),
            HelpContract(
                name="FalsificationVerdict",
                summary=(
                    "Exactly one of TESTABLE, BELOW_SENSITIVITY, NON_DISCRIMINATING, "
                    "or NOT_YET_FALSIFIABLE. It assigns no probability that the hypothesis is true."
                ),
            ),
            HelpContract(
                name="ScientificClaim",
                summary=(
                    "One claim with provenance measured, literature-derived, assumed, or simulated, "
                    "and epistemic status established, hypothesis, speculative, or unknown. "
                    "A measured claim names an observable. A number includes a unit. "
                    "A literature-derived claim names source_ref. A simulated claim names "
                    "spec_id and routine_id. Speculative status does not decide operationality. "
                    "There is no field for executable code."
                ),
            ),
        ],
        not_available=[
            "frontend",
            "database",
            "DQ-12 demo",
            "Duffing demo",
        ],
    )
