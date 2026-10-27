"""End-to-end falsification run. It calls the existing stages and adds none."""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.diagnostics.parser_response import describe_validation_error, redact, write_parser_failure
from app.diagnostics.run_checkpoint import ResumeRefused, ResumeSelection, write_run_checkpoint
from app.providers.meta import ConfigurationError, LiveModelCallsDisabled, ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.critic import CritiqueReport
from app.schemas.experiment import ExperimentPlanResult
from app.schemas.null_model import NullModelResult
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.schemas.run import (
    RUN_ID_PATTERN,
    FailureDiagnostic,
    RunRequest,
    RunResult,
    RunSummary,
    StageName,
    StageRecord,
    StageStatus,
    UsageSummary,
)
from app.schemas.simulation import SimulationPlanResult, SimulationResult
from app.schemas.verdict import FalsificationVerdict
from app.services.critic import critique_hypothesis
from app.services.demo_fixtures import register_demo_fixtures
from app.services.experiment import design_experiment
from app.services.judge import judge_hypothesis
from app.services.modes import ExecutionMode
from app.services.null_model import build_null_model
from app.services.observable import design_observables
from app.services.parser import parse_hypothesis
from app.services.reasoning import stage_effort
from app.services.simulation_plan import plan_simulation
from app.simulation.engine import SimulationRejected, run_simulation

register_demo_fixtures()

STAGE_NAMES: tuple[StageName, ...] = (
    "parser",
    "critic",
    "null_model",
    "observable",
    "simulation_plan",
    "simulation",
    "experiment",
    "judge",
)
RunIdFactory = Callable[[], str]


@dataclass(frozen=True)
class RunDiagnostics:
    """Optional development files. Production calls leave this unset."""

    checkpoint_path: Path
    parser_response_path: Path
    secret: str


class UsageTransport:
    """Count one live completion. It stores no headers and no reasoning text."""

    def __init__(self, inner: ModelTransport) -> None:
        self.inner = inner
        self.records: list[dict[str, int]] = []

    @property
    def last_body(self) -> object:
        return getattr(self.inner, "last_body", None)

    @property
    def last_http_status(self) -> int | None:
        return getattr(self.inner, "last_http_status", None)

    @property
    def last_usage(self) -> dict[str, int] | None:
        usage = getattr(self.inner, "last_usage", None)
        return usage if isinstance(usage, dict) else None

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> dict[str, object]:
        payload = self.inner.post_json(url=url, headers=headers, body=body)
        usage = getattr(self.inner, "last_usage", None) or {}
        self.records.append({key: value for key, value in usage.items() if isinstance(value, int)})
        return payload


def default_run_id() -> str:
    """A local identifier. The model does not choose it."""

    return "run_" + secrets.token_hex(8)


def execute_run(
    request: RunRequest,
    *,
    settings: Settings,
    transport: ModelTransport | None = None,
    run_id_factory: RunIdFactory = default_run_id,
    diagnostics: RunDiagnostics | None = None,
    resume: ResumeSelection | None = None,
) -> RunResult:
    """Run the verified pipeline once. A blocked simulation does not stop the judge."""

    if resume is not None:
        request = request.model_copy(update={"hypothesis": resume.hypothesis})
    run_id = run_id_factory()
    if re.fullmatch(RUN_ID_PATTERN, run_id) is None:
        raise ValueError("run id factory produced a non-canonical id")
    secret = settings.model_api_key.get_secret_value()
    started = time.perf_counter()
    stages = {name: StageRecord(name=name, status="pending") for name in STAGE_NAMES}
    meter = UsageTransport(transport) if request.mode is ExecutionMode.LIVE and transport is not None else None
    if request.mode is ExecutionMode.LIVE and meter is None:
        from app.providers.transport import UrllibTransport

        meter = UsageTransport(UrllibTransport())
    live_transport = meter if meter is not None else transport
    profile = request.reasoning_profile
    parsed: ParserResult | None = None
    critique: CritiqueReport | None = None
    null_model: NullModelResult | None = None
    observables: ObservableDesignResult | None = None
    simulation_plan: SimulationPlanResult | None = None
    simulation_result: SimulationResult | None = None
    experiment: ExperimentPlanResult | None = None
    verdict: FalsificationVerdict | None = None
    error: str | None = None
    calls_before = 0
    traced: dict[str, object] = {"hypothesis": request.hypothesis}
    simulation_skipped: bool | None = None

    def already_done(name: StageName) -> bool:
        return resume is not None and STAGE_NAMES.index(name) < STAGE_NAMES.index(resume.start)

    def remember(name: str | None = None, obj: object | None = None) -> None:
        if name is not None and obj is not None:
            traced[name] = obj
        if diagnostics is None:
            return
        write_run_checkpoint(
            diagnostics.checkpoint_path,
            traced,  # type: ignore[arg-type]
            secret=secret,
            simulation_skipped=simulation_skipped,
        )

    remember()

    def finish_stage(name: StageName, status: StageStatus, detail: str, began: float) -> None:
        nonlocal calls_before
        record = stages[name]
        record.status = status
        record.detail = detail
        record.elapsed_ms = int((time.perf_counter() - began) * 1000)
        if meter is not None:
            fresh = meter.records[calls_before:]
            calls_before = len(meter.records)
            for item in fresh:
                record.prompt_tokens += item.get("prompt_tokens", 0)
                record.completion_tokens += item.get("completion_tokens", 0)
                record.reasoning_tokens += item.get("reasoning_tokens", 0)
                record.total_tokens += item.get("total_tokens", 0)

    def fail(name: StageName, exc: BaseException, began: float) -> RunResult:
        diagnostic = getattr(exc, "diagnostic", None)
        if (
            diagnostics is not None
            and diagnostic is not None
            and isinstance(getattr(diagnostic, "content", None), str)
        ):
            destination = diagnostics.parser_response_path
            if name != "parser":
                destination = destination.with_name(f"live_run_{name}_response.json")
            write_parser_failure(
                destination,
                content=diagnostic.content,
                metadata=diagnostic.metadata if isinstance(diagnostic.metadata, dict) else {},
                validation_error=diagnostic.validation_error,
                secret=secret,
            )
        finish_stage(name, "failed", _public_error(exc, secret), began)
        _skip_after(stages, name)
        return _result(
            run_id,
            request,
            stages,
            parsed,
            critique,
            null_model,
            observables,
            simulation_plan,
            simulation_result,
            experiment,
            verdict,
            error=_public_error(exc, secret),
            failure=_failure_diagnostic(name, exc, secret),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            meter=meter,
        )

    began = time.perf_counter()
    if already_done("parser"):
        if resume is None or resume.parser is None:
            raise ResumeRefused("resume is missing a validated parser")
        parsed = resume.parser
        finish_stage("parser", "success", "Resumed from a validated checkpoint.", began)
    else:
        try:
            parsed = parse_hypothesis(
                request.hypothesis,
                mode=request.mode,
                settings=settings,
                transport=live_transport,
            )
        except (ConfigurationError, LiveModelCallsDisabled, ProviderResponseError, Exception) as exc:
            return fail("parser", exc, began)
        finish_stage("parser", "success", "", began)
    remember("parser", parsed)

    began = time.perf_counter()
    if already_done("critic"):
        if resume is None or resume.critique is None:
            raise ResumeRefused("resume is missing a validated critic")
        critique = resume.critique
        finish_stage("critic", "success", "Resumed from a validated checkpoint.", began)
    else:
        try:
            critique = critique_hypothesis(
                request.hypothesis,
                parsed,
                mode=request.mode,
                settings=settings,
                transport=live_transport,
                reasoning_effort=stage_effort(profile, "critic"),
            )
        except Exception as exc:
            return fail("critic", exc, began)
        finish_stage("critic", "success", "", began)
    remember("critic", critique)

    began = time.perf_counter()
    if already_done("null_model"):
        if resume is None or resume.null_model is None:
            raise ResumeRefused("resume is missing a validated null model")
        null_model = resume.null_model
        finish_stage("null_model", "success", "Resumed from a validated checkpoint.", began)
    else:
        try:
            null_model = build_null_model(
                request.hypothesis,
                parsed,
                critique,
                mode=request.mode,
                settings=settings,
                transport=live_transport,
                reasoning_effort=stage_effort(profile, "null_model"),
            )
        except Exception as exc:
            return fail("null_model", exc, began)
        finish_stage("null_model", "success", "", began)
    remember("null_model", null_model)

    began = time.perf_counter()
    if already_done("observable"):
        if resume is None or resume.observables is None:
            raise ResumeRefused("resume is missing a validated observable design")
        observables = resume.observables
    else:
        try:
            observables = design_observables(
                request.hypothesis,
                parsed,
                critique,
                null_model,
                mode=request.mode,
                settings=settings,
                transport=live_transport,
                reasoning_effort=stage_effort(profile, "observable"),
            )
        except Exception as exc:
            return fail("observable", exc, began)
    observable_state: StageStatus = (
        "success" if any(item.discriminating for item in observables.observables) else "blocked"
    )
    observable_detail = "" if observable_state == "success" else _first(observables.blocking_issues)
    if already_done("observable"):
        observable_detail = observable_detail or "Resumed from a validated checkpoint."
    finish_stage("observable", observable_state, observable_detail, began)
    remember("observable", observables)

    began = time.perf_counter()
    if already_done("simulation_plan"):
        if resume is None or resume.simulation_plan is None:
            raise ResumeRefused("resume is missing a validated simulation plan")
        simulation_plan = resume.simulation_plan
    else:
        try:
            simulation_plan = plan_simulation(
                request.hypothesis,
                parsed,
                critique,
                null_model,
                observables,
                mode=request.mode,
                settings=settings,
                transport=live_transport,
                reasoning_effort=stage_effort(profile, "simulation_plan"),
            )
        except Exception as exc:
            return fail("simulation_plan", exc, began)
    plan_state: StageStatus = "success" if simulation_plan.status == "ready" else "blocked"
    plan_detail = "" if plan_state == "success" else _first(simulation_plan.blocking_missing_definitions)
    if already_done("simulation_plan") and plan_state == "success":
        plan_detail = "Resumed from a validated checkpoint."
    finish_stage("simulation_plan", plan_state, plan_detail, began)
    remember("simulation_plan", simulation_plan)

    began = time.perf_counter()
    if already_done("simulation"):
        if resume is not None and resume.simulation is not None:
            simulation_result = resume.simulation
            simulation_skipped = False
            finish_stage("simulation", "success", "Resumed from a validated checkpoint.", began)
            remember("simulation", simulation_result)
        else:
            simulation_skipped = True
            finish_stage("simulation", "skipped", "The simulation plan is blocked.", began)
            remember()
    elif simulation_plan.status != "ready" or simulation_plan.spec is None:
        simulation_skipped = True
        finish_stage("simulation", "skipped", "The simulation plan is blocked.", began)
        remember()
    else:
        try:
            simulation_result = run_simulation(simulation_plan.spec)
        except (SimulationRejected, Exception) as exc:
            return fail("simulation", exc, began)
        simulation_skipped = False
        finish_stage("simulation", "success", "", began)
        remember("simulation", simulation_result)

    began = time.perf_counter()
    try:
        experiment = design_experiment(
            request.hypothesis,
            parsed,
            critique,
            null_model,
            observables,
            simulation_plan,
            simulation_result,
            mode=request.mode,
            settings=settings,
            transport=live_transport,
            reasoning_effort=stage_effort(profile, "experiment"),
        )
    except Exception as exc:
        return fail("experiment", exc, began)
    experiment_state: StageStatus = "blocked" if experiment.status == "blocked" else "success"
    experiment_detail = "" if experiment_state == "success" else _first(experiment.blocking_missing_definitions)
    finish_stage("experiment", experiment_state, experiment_detail, began)
    remember("experiment", experiment)

    began = time.perf_counter()
    try:
        verdict = judge_hypothesis(
            request.hypothesis,
            parsed,
            critique,
            null_model,
            observables,
            simulation_plan,
            simulation_result,
            experiment,
            None,
            mode=request.mode,
            settings=settings,
            transport=live_transport,
            reasoning_effort=stage_effort(profile, "judge"),
        )
    except Exception as exc:
        return fail("judge", exc, began)
    finish_stage("judge", "success", verdict.status, began)
    remember("judge", verdict)
    return _result(
        run_id,
        request,
        stages,
        parsed,
        critique,
        null_model,
        observables,
        simulation_plan,
        simulation_result,
        experiment,
        verdict,
        error=error,
        failure=None,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        meter=meter,
    )


def build_summary(
    *,
    hypothesis_text: str,
    parser_result: ParserResult | None,
    null_model: NullModelResult | None,
    observables: ObservableDesignResult | None,
    simulation_plan: SimulationPlanResult | None,
    simulation_result: SimulationResult | None,
    experiment: ExperimentPlanResult | None,
    verdict: FalsificationVerdict | None,
) -> RunSummary | None:
    """Read the summary from validated objects. It does not call a model."""

    if verdict is None or parser_result is None or null_model is None or experiment is None:
        return None
    claim = parser_result.claims[0].statement if parser_result.claims else hypothesis_text
    if null_model.models:
        null_text = null_model.models[0].description
    else:
        null_text = null_model.summary
    observable_text = None
    if observables is not None and observables.observables:
        chosen = next(
            (item for item in observables.observables if item.discriminating),
            observables.observables[0],
        )
        observable_text = f"{chosen.name}: {chosen.definition}"
    if simulation_result is not None:
        simulation_status = "ready"
    elif simulation_plan is not None:
        simulation_status = simulation_plan.status
    else:
        simulation_status = "not run"
    return RunSummary(
        claim=claim,
        null_model=null_text,
        observable=observable_text,
        simulation_status=simulation_status,
        experiment_status=experiment.status,
        verdict=verdict.status,
        primary_reason=verdict.primary_reason,
        required_next_definition=verdict.required_next_definition,
    )


def _result(
    run_id: str,
    request: RunRequest,
    stages: dict[StageName, StageRecord],
    parsed: ParserResult | None,
    critique,
    null_model: NullModelResult | None,
    observables: ObservableDesignResult | None,
    simulation_plan: SimulationPlanResult | None,
    simulation_result: SimulationResult | None,
    experiment: ExperimentPlanResult | None,
    verdict: FalsificationVerdict | None,
    *,
    error: str | None,
    failure: FailureDiagnostic | None,
    elapsed_ms: int,
    meter: UsageTransport | None,
) -> RunResult:
    summary = build_summary(
        hypothesis_text=request.hypothesis.statement,
        parser_result=parsed,
        null_model=null_model,
        observables=observables,
        simulation_plan=simulation_plan,
        simulation_result=simulation_result,
        experiment=experiment,
        verdict=verdict,
    )
    usage = _usage(meter, elapsed_ms)
    return RunResult(
        run_id=run_id,
        status=_outcome(stages, verdict, error),
        hypothesis_text=request.hypothesis.statement,
        stages=[stages[name] for name in STAGE_NAMES],
        parser=parsed,
        critique=critique,
        null_model=null_model,
        observable_design=observables,
        simulation_plan=simulation_plan,
        simulation_result=simulation_result,
        experiment=experiment,
        verdict=verdict,
        summary=summary,
        usage=usage,
        error=error,
        failure=failure,
    )


def _outcome(stages: dict[StageName, StageRecord], verdict: FalsificationVerdict | None, error: str | None):
    if error is not None or any(item.status == "failed" for item in stages.values()):
        return "failed"
    if verdict is None:
        return "failed"
    if verdict.status == "NOT_YET_FALSIFIABLE":
        return "scientifically_blocked"
    if stages["observable"].status == "blocked" or stages["experiment"].status == "blocked":
        return "scientifically_blocked"
    return "completed"


def _usage(meter: UsageTransport | None, elapsed_ms: int) -> UsageSummary:
    if meter is None:
        return UsageSummary(elapsed_ms=elapsed_ms)
    prompt = completion = reasoning = total = 0
    for item in meter.records:
        prompt += item.get("prompt_tokens", 0)
        completion += item.get("completion_tokens", 0)
        reasoning += item.get("reasoning_tokens", 0)
        total += item.get("total_tokens", 0)
    return UsageSummary(
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=reasoning,
        total_tokens=total,
        model_calls=len(meter.records),
        elapsed_ms=elapsed_ms,
    )


def _skip_after(stages: dict[StageName, StageRecord], failed: StageName) -> None:
    seen = False
    for name in STAGE_NAMES:
        if name == failed:
            seen = True
            continue
        if seen and stages[name].status == "pending":
            stages[name].status = "skipped"


def _failure_diagnostic(stage: StageName, exc: BaseException, secret: str) -> FailureDiagnostic:
    diagnostic = getattr(exc, "diagnostic", None)
    kind = getattr(diagnostic, "failure_kind", None)
    if kind in {"schema_validation", "json_decode"}:
        paths: list[str] = []
        validation_error = getattr(diagnostic, "validation_error", None)
        if validation_error is not None:
            paths = [row["path"] for row in describe_validation_error(validation_error, secret=secret)]
        message = (
            "Parser response did not satisfy ParserResult"
            if stage == "parser"
            else f"{stage} response did not satisfy its schema"
        )
        return FailureDiagnostic(
            stage=stage,
            failure_kind=kind,
            safe_message=message,
            validation_paths=paths,
        )
    return FailureDiagnostic(
        stage=stage,
        failure_kind="system",
        safe_message=_public_error(exc, secret),
        validation_paths=[],
    )


def _public_error(exc: BaseException, secret: str) -> str:
    text = redact(f"{type(exc).__name__}: {exc}", secret)
    text = text.replace("\n", " ")
    return text[:500]


def _first(items: list[str]) -> str:
    return items[0] if items else ""
