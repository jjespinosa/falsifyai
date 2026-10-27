"""Diagnostics for a parser response. These tests do not call the network."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.diagnostics.parser_response import (
    compare_parser_schemas,
    completion_facts,
    content_profile,
    describe_validation_error,
    parser_contract_audit,
    redact,
    render_validation_diagnostic,
    semantic_rules,
    validator_index,
    write_parser_failure,
    write_structured_response,
)
from app.schemas.parser import ParserResult

_SECRET = "LLM_diagnostic_test_secret"


def test_validation_diagnostic_reports_path_type_and_hides_the_value() -> None:
    with pytest.raises(ValidationError) as captured:
        ParserResult.model_validate(
            {
                "claims": [
                    {
                        "claim_id": "C1",
                        "statement": _SECRET,
                        "claim_type": "causal",
                        "is_operational": False,
                        "epistemic_status": "hypothesis",
                        "provenance": {"origin": "measured"},
                        "confidence": "low",
                    }
                ]
            }
        )

    rendered = render_validation_diagnostic(captured.value)
    rows = describe_validation_error(captured.value)

    assert rows
    assert "validation_error_count:" in rendered
    assert any(row["field"] == "claim_id" and "pattern" in row["type"] for row in rows)
    assert any(row["path"] == "claims.0.provenance" for row in rows)
    assert any(row["value"] == "C1" for row in rows)
    assert any("measured claim requires an observable" in row["message"] for row in rows)
    assert all(row["value_type"] and row["value"] for row in rows)
    assert _SECRET not in rendered


def test_schema_comparison_shows_inlining_and_expanded_required() -> None:
    report = compare_parser_schemas()
    differences = "\n".join(report["differences"])

    assert report["sent_equals_transformed"] is True
    assert report["raw_ref_count"] > 0
    assert report["transformed_ref_count"] == 0
    assert "$ref nodes" in differences
    assert "ParserResult required differs" in differences
    assert "added=['assumptions', 'parser_notes', 'undefined_terms']" in differences
    assert "enums differ" not in differences
    assert "nullable fields differ" not in differences
    assert "properties differ" not in differences


def test_semantic_catalog_covers_every_custom_validator() -> None:
    catalog = {(rule.model, rule.validator) for rule in semantic_rules()}

    assert catalog == validator_index()
    assert all(rule.in_json_schema is False for rule in semantic_rules())
    provenance = next(
        rule
        for rule in semantic_rules()
        if rule.model == "ClaimProvenance" and rule.validator == "_check_provenance"
    )
    assert "measured claim requires an observable" in provenance.rule
    assert "literature-derived claim requires source_ref" in provenance.rule


def test_content_profile_counts_arrays_and_string_lengths() -> None:
    payload = {
        "claims": [{"statement": "period grows with length"}],
        "assumptions": [],
        "undefined_terms": [{"term": "regime"}],
        "parser_notes": ["one note"],
    }

    profile = content_profile(payload, json.dumps(payload))

    assert profile["claims"] == 1
    assert profile["assumptions"] == 0
    assert profile["undefined_terms"] == 1
    assert profile["parser_notes"] == 1
    assert profile["top_level_keys"] == [
        "assumptions",
        "claims",
        "parser_notes",
        "undefined_terms",
    ]
    assert profile["array_lengths"]["$.claims"] == 1
    assert profile["longest_strings"][0]["path"] == "$.claims[0].statement"
    assert profile["longest_strings"][0]["length"] == len("period grows with length")


def test_saved_response_and_facts_do_not_keep_a_secret(tmp_path: Path) -> None:
    destination = tmp_path / "live_parser_response.json"
    write_structured_response(
        destination,
        json.dumps({"statement": f"see {_SECRET}", "note": "Bearer super-secret-token"}),
        secret=_SECRET,
    )
    saved = destination.read_text(encoding="utf-8")

    assert _SECRET not in saved
    assert "super-secret-token" not in saved
    assert "[redacted]" in saved
    facts = completion_facts(
        {
            "model": "muse-spark-1.3",
            "choices": [{"finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 4,
                "total_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
        },
        http_status=200,
    )
    rendered = redact(json.dumps(facts), _SECRET)
    assert facts["http_status"] == 200
    assert facts["finish_reason"] == "stop"
    assert facts["model"] == "muse-spark-1.3"
    assert facts["reasoning_tokens"] == 2
    assert facts["total_tokens"] == 7
    assert _SECRET not in rendered


def test_live_pendulum_parser_payload_keeps_the_operational_variable_rule() -> None:
    """The captured Muse payload is operational while every named quantity is undefined."""

    from app.prompts.parser import PARSER_SYSTEM_PROMPT

    payload = {
        "assumptions": [],
        "claims": [
            {
                "assumptions": [],
                "claim_id": "c1",
                "claim_type": "causal",
                "confidence": "high",
                "epistemic_status": "hypothesis",
                "is_operational": True,
                "missing_definitions": [
                    {
                        "critical": False,
                        "statement": "Threshold defining 'small-angle regime' (e.g., maximum angular amplitude) is not specified.",
                    }
                ],
                "provenance": {
                    "observable": None,
                    "origin": "assumed",
                    "routine_id": None,
                    "source_ref": None,
                    "spec_id": None,
                    "unit": None,
                    "value": None,
                },
                "statement": "At fixed pendulum length and within the small-angle regime, increasing the bob mass changes the oscillation period.",
                "variables": [
                    {"defined": False, "name": "bob mass", "unit": None},
                    {"defined": False, "name": "oscillation period", "unit": None},
                    {"defined": False, "name": "pendulum length", "unit": None},
                ],
            }
        ],
        "parser_notes": [],
        "undefined_terms": [],
    }
    with pytest.raises(ValidationError) as captured:
        ParserResult.model_validate(payload)

    rows = describe_validation_error(captured.value)
    assert len(rows) == 1
    assert rows[0]["path"] == "claims.0"
    assert rows[0]["type"] == "value_error"
    assert rows[0]["message"] == "Value error, an operational claim cannot include an undefined variable"
    assert "defined=true does not require that quantitative specification." in PARSER_SYSTEM_PROMPT
    assert "Do not encode missing numerical information by setting defined=false." in PARSER_SYSTEM_PROMPT
    assert "If any variable has defined set to false, set is_operational to false." in PARSER_SYSTEM_PROMPT


def test_parser_contract_audit_keeps_post_schema_rules() -> None:
    audit = parser_contract_audit()

    assert audit["claim_id_pattern_sent"] is True
    assert audit["assumption_id_pattern_sent"] is True
    assert audit["sent_equals_transformed"] is True
    for name in (
        "blank-string rejection",
        "finite numeric values",
        "unique ids",
        "provenance cross-field rules",
        "epistemic/operational rules",
        "critical missing definitions",
        "evidence grounding against user input",
    ):
        assert name in audit["absent"]
    assert all(rule.in_json_schema is False for rule in semantic_rules())
    assert "ensure_stated_evidence.stated_number_and_source" in audit["absent_validators"]


def test_parser_failure_file_keeps_the_structured_message_and_drops_the_secret(tmp_path: Path) -> None:
    destination = tmp_path / "live_run_parser_response.json"
    content = json.dumps(
        {
            "claims": [
                {
                    "claim_id": "C1",
                    "statement": f"see {_SECRET}",
                    "note": "Bearer super-secret-token",
                }
            ]
        }
    )
    with pytest.raises(ValidationError) as captured:
        ParserResult.model_validate(json.loads(content))
    write_parser_failure(
        destination,
        content=content,
        metadata={
            "http_status": 200,
            "finish_reason": "stop",
            "model": "muse-spark-1.3",
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "reasoning_tokens": 1,
            "total_tokens": 14,
        },
        validation_error=captured.value,
        secret=_SECRET,
    )
    saved = destination.read_text(encoding="utf-8")
    document = json.loads(saved)

    assert _SECRET not in saved
    assert "super-secret-token" not in saved
    assert "Authorization" not in saved
    assert document["metadata"]["http_status"] == 200
    assert document["metadata"]["finish_reason"] == "stop"
    assert document["metadata"]["reasoning_tokens"] == 1
    assert document["metadata"]["top_level_keys"] == ["claims"]
    assert document["content"]["claims"][0]["claim_id"] == "C1"
    assert any(row["path"] == "claims.0.claim_id" and row["value"] == "C1" for row in document["validation_errors"])
    with pytest.raises(ValidationError) as replayed:
        ParserResult.model_validate(document["content"])
    assert any(error["loc"] == ("claims", 0, "claim_id") for error in replayed.value.errors())


def test_diagnostic_helpers_do_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during parser diagnostic")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    compare_parser_schemas()
    semantic_rules()
