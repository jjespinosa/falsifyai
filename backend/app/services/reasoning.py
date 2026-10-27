"""Public reasoning profiles for one end-to-end run.

The run API exposes economy and balanced. Individual services can still
receive an effort argument, and neither profile uses high or xhigh.
"""

from __future__ import annotations

from typing import Literal

ReasoningProfile = Literal["economy", "balanced"]
Effort = Literal["minimal", "low", "medium"]

_ECONOMY: dict[str, Effort] = {
    "parser": "minimal",
    "critic": "low",
    "null_model": "low",
    "observable": "low",
    "simulation_plan": "low",
    "experiment": "low",
    "judge": "low",
}

_BALANCED: dict[str, Effort] = {
    "parser": "minimal",
    "critic": "low",
    "null_model": "medium",
    "observable": "medium",
    "simulation_plan": "medium",
    "experiment": "medium",
    "judge": "medium",
}


def stage_effort(profile: ReasoningProfile, stage: str) -> Effort:
    """Return the effort for one model stage. Parser stays minimal in both profiles."""

    table = _ECONOMY if profile == "economy" else _BALANCED
    if stage not in table:
        raise ValueError("unknown reasoning stage")
    return table[stage]
