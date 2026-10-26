"""Null-model builder. Stub mode is deterministic. Live mode does not fall back."""

from __future__ import annotations

from app.config import Settings
from app.prompts.null_model import NULL_MODEL_SYSTEM_PROMPT, null_model_user_prompt
from app.providers.meta import ProviderResponseError
from app.providers.transport import ModelTransport
from app.schemas.critic import CritiqueReport
from app.schemas.hypothesis import HypothesisInput
from app.schemas.null_model import (
    KnowledgeBasis,
    NullModel,
    NullModelResult,
    require_known_targets,
)
from app.schemas.parser import ParserResult
from app.services.grounding import (
    InventedEvidenceError,
    ensure_no_invented_unit_values,
    iter_text,
)
from app.services.live import complete_structured
from app.services.m2_fixtures import GOLDEN_M2_CLAIM_IDS, GOLDEN_NULLS
from app.services.modes import ExecutionMode
from app.services.fixtures import normalize_statement


def build_null_model(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    critique_report: CritiqueReport,
    *,
    mode: ExecutionMode,
    settings: Settings,
    transport: ModelTransport | None = None,
    reasoning_effort: str = "medium",
) -> NullModelResult:
    """Build H0. A live failure stays a live failure."""

    if mode is ExecutionMode.STUB:
        result = _stub_null(hypothesis, parser_result, critique_report)
    elif mode is ExecutionMode.LIVE:
        result = complete_structured(
            settings,
            transport,
            system=NULL_MODEL_SYSTEM_PROMPT,
            user=null_model_user_prompt(
                hypothesis_payload=hypothesis.model_dump_json(),
                parser_payload=parser_result.model_dump_json(),
                critique_payload=critique_report.model_dump_json(),
            ),
            schema_name="NullModelResult",
            model=NullModelResult,
            reasoning_effort=reasoning_effort,
        )
    else:
        raise ValueError("unsupported execution mode")
    _guard(hypothesis, parser_result, result)
    return result


def _guard(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    result: NullModelResult,
) -> None:
    known = {claim.claim_id for claim in parser_result.claims}
    try:
        for model in result.models:
            require_known_targets(model.target_claim_ids, known, label="target_claim_ids")
        ensure_no_invented_unit_values(hypothesis, iter_text(result.model_dump(mode="json")))
    except (ValueError, InventedEvidenceError) as exc:
        raise ProviderResponseError(str(exc)) from None


def _stub_null(
    hypothesis: HypothesisInput,
    parser_result: ParserResult,
    critique_report: CritiqueReport,
) -> NullModelResult:
    key = normalize_statement(hypothesis.statement)
    builder = GOLDEN_NULLS.get(key)
    expected = GOLDEN_M2_CLAIM_IDS.get(key)
    claim_ids = {claim.claim_id for claim in parser_result.claims}
    if builder is not None and expected is not None and expected <= claim_ids:
        return builder()
    return _generic_null(parser_result, critique_report)


def _generic_null(parser_result: ParserResult, critique_report: CritiqueReport) -> NullModelResult:
    blockers: list[str] = []
    for claim in parser_result.claims:
        for item in claim.missing_definitions:
            if item.critical and item.statement not in blockers:
                blockers.append(item.statement)
    for note in critique_report.required_clarifications:
        if note not in blockers:
            blockers.append(note)
    if not blockers:
        blockers.append("The supplied claims do not define a quantity H0 can be aimed at.")
    return NullModelResult(
        models=[
            NullModel(
                model_id="h0",
                description=(
                    "No conventional competing model was constructed from the supplied definitions."
                ),
                target_claim_ids=[claim.claim_id for claim in parser_result.claims],
                can_mimic_claim=False,
                mimicry_reason=(
                    "The available definitions do not identify an effect a conventional "
                    "model could reproduce."
                ),
                limitations=["No measurement or equation was added."],
                basis=KnowledgeBasis.COMPARISON_ASSUMPTION,
                blocking_missing_definitions=blockers,
            )
        ],
        summary=(
            "A meaningful null model is blocked by missing definitions. "
            "No competing mechanism was invented."
        ),
    )
