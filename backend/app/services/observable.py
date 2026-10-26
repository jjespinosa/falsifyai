"""Observable designer. Stub mode is deterministic. Live mode does not fall back."""

from __future__ import annotations

from app.config import Settings
from app.prompts.observable import OBSERVABLE_SYSTEM_PROMPT, observable_user_prompt
from app.providers.meta import ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.critic import CritiqueReport
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import NullModelResult, require_known_targets
from app.schemas.observable import ObservableDesignResult
from app.schemas.parser import ParserResult
from app.services.grounding import (
    InventedEvidenceError,
    ensure_no_invented_unit_values,
    iter_text,
)
from app.services.live import complete_structured
from app.services.m2_fixtures import GOLDEN_M2_CLAIM_IDS, GOLDEN_OBSERVABLES
from app.services.modes import ExecutionMode
from app.services.fixtures import normalize_statement


def design_observables(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    critique_report: CritiqueReport,
    null_model_result: NullModelResult,
    *,
    mode: ExecutionMode,
    settings: Settings,
    transport: ModelTransport | None = None,
    reasoning_effort: str = "medium",
) -> ObservableDesignResult:
    """Propose observables that might separate H1 from H0."""

    if mode is ExecutionMode.STUB:
        result = _stub_design(hypothesis, parser_result, null_model_result)
    elif mode is ExecutionMode.LIVE:
        result = complete_structured(
            settings,
            transport,
            system=OBSERVABLE_SYSTEM_PROMPT,
            user=observable_user_prompt(
                hypothesis_payload=hypothesis.model_dump_json(),
                parser_payload=parser_result.model_dump_json(),
                critique_payload=critique_report.model_dump_json(),
                null_model_payload=null_model_result.model_dump_json(),
            ),
            schema_name="ObservableDesignResult",
            model=ObservableDesignResult,
            reasoning_effort=reasoning_effort,
        )
    else:
        raise ValueError("unsupported execution mode")
    _guard(hypothesis, parser_result, result)
    return result


def _guard(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    result: ObservableDesignResult,
) -> None:
    known = {claim.claim_id for claim in parser_result.claims}
    try:
        for candidate in result.observables:
            require_known_targets(candidate.target_claim_ids, known, label="target_claim_ids")
        ensure_no_invented_unit_values(hypothesis, iter_text(result.model_dump(mode="json")))
    except (ValueError, InventedEvidenceError) as exc:
        raise ProviderResponseError(str(exc)) from None


def _stub_design(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    null_model_result: NullModelResult,
) -> ObservableDesignResult:
    key = normalize_statement(hypothesis.statement)
    builder = GOLDEN_OBSERVABLES.get(key)
    expected = GOLDEN_M2_CLAIM_IDS.get(key)
    claim_ids = {claim.claim_id for claim in parser_result.claims}
    if builder is not None and expected is not None and expected <= claim_ids:
        return builder()
    blockers: list[str] = []
    for model in null_model_result.models:
        for item in model.blocking_missing_definitions:
            if item not in blockers:
                blockers.append(item)
    if not blockers:
        blockers.append("No quantity is defined well enough to separate H1 from H0.")
    return ObservableDesignResult(
        observables=[],
        blocking_issues=blockers,
        summary=(
            "No discriminating observable follows until the missing definitions are supplied."
        ),
    )
