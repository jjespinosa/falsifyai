"""Null-model and observable tests. None of these open a socket."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import load_settings
from app.main import create_app
from app.prompts.null_model import NULL_MODEL_SYSTEM_PROMPT
from app.prompts.observable import OBSERVABLE_SYSTEM_PROMPT
from app.providers.meta import ProviderResponseError
from app.providers.schema_json import strict_json_schema, strict_subset_issues
from app.schemas.claim import ClaimProvenance, EpistemicStatus, EvidenceOrigin
from app.schemas.critic import CritiqueIssue, IssueCategory, IssueSeverity, assemble_report
from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import (
    ClaimType,
    ClaimVariable,
    ExtractionConfidence,
    ParsedClaim,
    ParserResult,
)
from app.schemas.identifiers import NULL_MODEL_ID_PATTERN, OBSERVABLE_ID_PATTERN
from app.schemas.null_model import NullModel, NullModelResult, require_known_targets
from app.schemas.observable import ObservableCandidate, ObservableDesignResult, PredictedDifference
from app.services.fixtures import (
    case_b_critic,
    case_b_parser,
    case_c_critic,
    case_c_parser,
    normalize_statement,
)
from app.services.m2_fixtures import (
    CASE_MASS,
    case_b_null,
    case_b_observable,
    case_c_null,
    case_c_observable,
    case_mass_null,
    case_mass_observable,
)
from app.services.modes import ExecutionMode
from app.services.null_model import build_null_model
from app.services.observable import design_observables

_FAKE_KEY = "unit-test-not-a-secret"
_FORBIDDEN_FIELDS = ("verdict", "falsified", "p_value", "significance", "not_yet_falsifiable")


def _has_forbidden_field(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in _FORBIDDEN_FIELDS or _has_forbidden_field(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_forbidden_field(item) for item in value)
    return False


class GuardTransport:
    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        del url, headers, body
        raise AssertionError("stub mode called the network transport")


class RecordingTransport:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict:
        self.calls.append({"url": url, "headers": dict(headers), "body": body})
        raise self.error


def _mass_bundle():
    hypothesis = HypothesisInput(statement=CASE_MASS)
    parsed = ParserResult(
        claims=[
            ParsedClaim(
                claim_id="c1",
                statement=CASE_MASS,
                claim_type=ClaimType.CAUSAL,
                variables=[
                    ClaimVariable(name="bob mass", defined=True),
                    ClaimVariable(name="oscillation period", unit="s", defined=True),
                ],
                is_operational=True,
                provenance=ClaimProvenance(origin=EvidenceOrigin.ASSUMED),
                epistemic_status=EpistemicStatus.HYPOTHESIS,
                confidence=ExtractionConfidence.MEDIUM,
            )
        ]
    )
    critique = assemble_report(
        issues=[
            CritiqueIssue(
                issue_id="i1",
                severity=IssueSeverity.MINOR,
                category=IssueCategory.MISSING_CONTROL,
                statement="Bob size is not stated to be fixed.",
                affected_claim_ids=["c1"],
                evidence_basis="The hypothesis does not mention bob size.",
                blocking=False,
            )
        ],
        summary="The mass claim needs a comparison that holds length and angle fixed.",
    )
    return hypothesis, parsed, critique


def test_null_and_observable_schemas_fit_strict_output() -> None:
    for model in (NullModelResult, ObservableDesignResult):
        schema = strict_json_schema(model)
        rendered = json.dumps(schema)
        assert strict_subset_issues(schema) == []
        assert "$ref" not in rendered
        assert _has_forbidden_field(schema["properties"]) is False
        assert "NOT_YET_FALSIFIABLE" not in rendered
        assert "TESTABLE" not in rendered
    assert NULL_MODEL_ID_PATTERN in json.dumps(strict_json_schema(NullModelResult))
    assert OBSERVABLE_ID_PATTERN in json.dumps(strict_json_schema(ObservableDesignResult))
    assert "You are the Null Model Builder inside FalsifyAI." in NULL_MODEL_SYSTEM_PROMPT
    assert "You are the Observable Designer inside FalsifyAI." in OBSERVABLE_SYSTEM_PROMPT


def test_canonical_ids_reject_uppercase() -> None:
    model = case_mass_null().models[0]
    observable = case_mass_observable().observables[0]
    assert model.model_id == "h0"
    assert observable.observable_id == "o1"
    uppercase = model.model_dump()
    uppercase["model_id"] = "H0"
    with pytest.raises(ValidationError):
        NullModel.model_validate(uppercase)
    bad_observable = observable.model_dump()
    bad_observable["observable_id"] = "O1"
    with pytest.raises(ValidationError):
        ObservableCandidate.model_validate(bad_observable)
    bad_observable["observable_id"] = "o0"
    with pytest.raises(ValidationError):
        ObservableCandidate.model_validate(bad_observable)
    accepted = model.model_dump()
    accepted["model_id"] = "h0_drag"
    NullModel.model_validate(accepted)


def test_duplicate_ids_and_unknown_targets_are_rejected() -> None:
    result = case_mass_null().model_dump()
    result["models"].append(result["models"][0])
    with pytest.raises(ValidationError, match="model_id"):
        NullModelResult.model_validate(result)
    design = case_mass_observable().model_dump()
    design["observables"].append(design["observables"][0])
    with pytest.raises(ValidationError, match="observable_id"):
        ObservableDesignResult.model_validate(design)
    with pytest.raises(ValueError, match="target_claim_ids"):
        require_known_targets(["c9"], {"c1"}, label="target_claim_ids")


def test_golden_null_models_cover_mimicry_and_blockers() -> None:
    mass = case_mass_null().models[0]
    blocked = case_b_null().models[0]
    confounded = case_c_null().models[0]

    assert mass.can_mimic_claim is True
    assert mass.known_confounders
    assert mass.equations[0].basis.value == "standard_knowledge"
    assert blocked.blocking_missing_definitions
    assert blocked.equations == []
    assert blocked.can_mimic_claim is False
    assert "light" in confounded.known_confounders
    assert confounded.can_mimic_claim is True
    for result in (case_mass_null(), case_b_null(), case_c_null()):
        assert _has_forbidden_field(result.model_dump()) is False


def test_observable_goldens_discriminate_only_when_the_models_differ() -> None:
    mass = case_mass_observable()
    blocked = case_b_observable()
    confounded = case_c_observable()

    assert mass.observables[0].discriminating is True
    assert mass.observables[0].required_controls
    assert mass.observables[0].predicted_difference is PredictedDifference.QUALITATIVE_DIFFERENCE
    assert blocked.observables == []
    assert blocked.blocking_issues
    assert confounded.observables == []
    assert confounded.blocking_issues
    undiscriminating = mass.observables[0].model_dump()
    undiscriminating["predicted_difference"] = PredictedDifference.ZERO.value
    with pytest.raises(ValidationError, match="different H1 and H0"):
        ObservableCandidate.model_validate(undiscriminating)


def test_stub_builder_and_designer_do_not_call_out() -> None:
    hypothesis, parsed, critique = _mass_bundle()
    settings = load_settings({})
    null_result = build_null_model(
        hypothesis,
        parsed,
        critique,
        mode=ExecutionMode.STUB,
        settings=settings,
        transport=GuardTransport(),
    )
    design = design_observables(
        hypothesis,
        parsed,
        critique,
        null_result,
        mode=ExecutionMode.STUB,
        settings=settings,
        transport=GuardTransport(),
    )

    assert null_result.models[0].model_id == "h0"
    assert design.observables[0].observable_id == "o1"
    vague = HypothesisInput(statement="Something unspecified happens.")
    empty = design_observables(
        vague,
        case_b_parser(vague),
        case_b_critic(),
        case_b_null(),
        mode=ExecutionMode.STUB,
        settings=settings,
    )
    assert empty.observables == []


def test_service_rejects_a_target_the_parser_did_not_return(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import m2_fixtures

    def bad() -> NullModelResult:
        result = case_mass_null()
        updated = result.models[0].model_copy(update={"target_claim_ids": ["c9"]})
        return result.model_copy(update={"models": [updated]})

    monkeypatch.setitem(m2_fixtures.GOLDEN_NULLS, normalize_statement(CASE_MASS), bad)
    hypothesis, parsed, critique = _mass_bundle()
    with pytest.raises(ProviderResponseError, match="target_claim_ids"):
        build_null_model(
            hypothesis,
            parsed,
            critique,
            mode=ExecutionMode.STUB,
            settings=load_settings({}),
        )


def test_null_model_and_observable_routes_default_to_stub_and_hide_the_key() -> None:
    hypothesis, parsed, critique = _mass_bundle()
    null_result = case_mass_null()
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": _FAKE_KEY,
                    "META_BASE_URL": "https://example.test/v1",
                    "META_MODEL_ID": "muse-spark-1.3",
                }
            ),
            live_transport=GuardTransport(),
        )
    )
    null_response = client.post(
        "/api/v1/analyze/null-model",
        json={
            "hypothesis": hypothesis.model_dump(mode="json"),
            "parser_result": parsed.model_dump(mode="json"),
            "critique_report": critique.model_dump(mode="json"),
        },
    )
    observable_response = client.post(
        "/api/v1/analyze/observable",
        json={
            "hypothesis": hypothesis.model_dump(mode="json"),
            "parser_result": parsed.model_dump(mode="json"),
            "critique_report": critique.model_dump(mode="json"),
            "null_model_result": null_result.model_dump(mode="json"),
        },
    )

    assert null_response.status_code == 200
    assert null_response.json()["models"][0]["can_mimic_claim"] is True
    assert observable_response.status_code == 200
    assert observable_response.json()["observables"][0]["discriminating"] is True
    assert _FAKE_KEY not in null_response.text
    assert _FAKE_KEY not in observable_response.text
    assert _has_forbidden_field(null_response.json()) is False
    assert _has_forbidden_field(observable_response.json()) is False


def test_live_m2_requests_use_medium_effort_and_do_not_fall_back() -> None:
    hypothesis, parsed, critique = _mass_bundle()
    transport = RecordingTransport(error=ProviderResponseError("live call failed"))
    client = TestClient(
        create_app(
            load_settings(
                {
                    "MODEL_API_KEY": _FAKE_KEY,
                    "META_BASE_URL": "https://api.meta.ai/v1",
                    "META_MODEL_ID": "muse-spark-1.3",
                }
            ),
            live_transport=transport,
        )
    )
    response = client.post(
        "/api/v1/analyze/null-model?mode=live",
        json={
            "hypothesis": hypothesis.model_dump(mode="json"),
            "parser_result": parsed.model_dump(mode="json"),
            "critique_report": critique.model_dump(mode="json"),
        },
    )

    assert response.status_code == 502
    assert "models" not in response.json()
    body = transport.calls[0]["body"]
    assert body["reasoning_effort"] == "medium"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert _FAKE_KEY not in json.dumps(body)
    refused = client.post(
        "/api/v1/analyze/observable?mode=live&reasoning_effort=none",
        json={
            "hypothesis": hypothesis.model_dump(mode="json"),
            "parser_result": parsed.model_dump(mode="json"),
            "critique_report": critique.model_dump(mode="json"),
            "null_model_result": case_mass_null().model_dump(mode="json"),
        },
    )
    assert refused.status_code == 422
    assert len(transport.calls) == 1


def test_case_b_and_case_c_stub_chain() -> None:
    settings = load_settings({})
    for statement, parse, critique in (
        ("Quantum biofield resonance improves systemic healing.", case_b_parser, case_b_critic),
        (
            "Tomato plants grow faster beside this speaker because the music "
            "transfers vital energy into their cells.",
            case_c_parser,
            case_c_critic,
        ),
    ):
        hypothesis = HypothesisInput(statement=statement)
        parsed = parse(hypothesis)
        report = critique()
        null_result = build_null_model(
            hypothesis, parsed, report, mode=ExecutionMode.STUB, settings=settings
        )
        design = design_observables(
            hypothesis,
            parsed,
            report,
            null_result,
            mode=ExecutionMode.STUB,
            settings=settings,
        )
        assert null_result.models
        assert design.observables == []
        assert design.blocking_issues
