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
    redact,
    render_validation_diagnostic,
    semantic_rules,
    validator_index,
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
    assert any("measured claim requires an observable" in row["message"] for row in rows)
    assert all(row["value_type"] for row in rows)
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
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        },
        http_status=200,
    )
    rendered = redact(json.dumps(facts), _SECRET)
    assert facts["http_status"] == 200
    assert facts["finish_reason"] == "stop"
    assert facts["model"] == "muse-spark-1.3"
    assert facts["total_tokens"] == 7
    assert _SECRET not in rendered


def test_diagnostic_helpers_do_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during parser diagnostic")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    compare_parser_schemas()
    semantic_rules()
