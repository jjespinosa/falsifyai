"""Reject numbers and citations that the user did not write."""

from __future__ import annotations

import re

from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import ParserResult

_TOKEN = r"(?<![\d.]){token}(?![\d.])"


class InventedEvidenceError(ValueError):
    """A parsed value or source does not appear in the hypothesis text."""


def hypothesis_source(hypothesis: HypothesisInput) -> str:
    parts = [
        hypothesis.statement,
        hypothesis.domain or "",
        hypothesis.context or "",
        *hypothesis.assumptions,
    ]
    return "\n".join(parts)


def ensure_stated_evidence(hypothesis: HypothesisInput, result: ParserResult) -> None:
    """Keep measured numbers and citations inside the text the user supplied."""

    source = hypothesis_source(hypothesis)
    for claim in result.claims:
        value = claim.provenance.value
        if value is not None and not _number_is_stated(value, source):
            raise InventedEvidenceError(
                "A parsed numeric value does not appear in the hypothesis text."
            )
        source_ref = claim.provenance.source_ref
        if source_ref is not None and source_ref not in source:
            raise InventedEvidenceError(
                "A parsed source does not appear in the hypothesis text."
            )


def _number_is_stated(value: float, source: str) -> bool:
    tokens = {str(value), f"{value:.12g}"}
    if float(value).is_integer():
        tokens.add(str(int(value)))
    return any(
        re.search(_TOKEN.format(token=re.escape(token)), source) is not None for token in tokens
    )
