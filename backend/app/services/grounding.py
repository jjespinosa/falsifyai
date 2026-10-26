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


_UNIT_VALUE = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)(?:\s*)(s|m|kg|g|hz|rad|cm|mm)\b",
    re.IGNORECASE,
)


def ensure_no_invented_unit_values(hypothesis: HypothesisInput, texts: list[str]) -> None:
    """Reject a quantity-with-unit that the user did not write."""

    source = hypothesis_source(hypothesis)
    for text in texts:
        for match in _UNIT_VALUE.finditer(text):
            if not _number_is_stated(float(match.group(1)), source):
                raise InventedEvidenceError(
                    "A generated quantity with a unit does not appear in the hypothesis text."
                )


def iter_text(value: object) -> list[str]:
    """Collect strings from a JSON-like tree."""

    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return found


def _number_is_stated(value: float, source: str) -> bool:
    tokens = {str(value), f"{value:.12g}"}
    if float(value).is_integer():
        tokens.add(str(int(value)))
    return any(
        re.search(_TOKEN.format(token=re.escape(token)), source) is not None for token in tokens
    )
