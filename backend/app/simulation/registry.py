"""Registered numerical families. Model text is never executed."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

PARAMETER_NAMES = (
    "value",
    "slope",
    "intercept",
    "quadratic",
    "amplitude",
    "rate",
    "offset",
)

FAMILIES: dict[str, tuple[str, ...]] = {
    "constant": ("value",),
    "linear": ("slope", "intercept"),
    "quadratic": ("quadratic", "slope", "intercept"),
    "exponential_decay": ("amplitude", "rate", "offset"),
}


def active_parameters(family: str, parameters: Mapping[str, float | None]) -> dict[str, float]:
    """Return the required finite parameters for one registered family."""

    required = FAMILIES.get(family)
    if required is None:
        raise ValueError(f"unknown model family: {family}")
    unknown = [name for name in parameters if name not in PARAMETER_NAMES]
    if unknown:
        raise ValueError(f"extra family parameter: {unknown[0]}")
    missing = [name for name in required if parameters.get(name) is None]
    if missing:
        raise ValueError(f"missing family parameter: {missing[0]}")
    extra = [
        name
        for name, value in parameters.items()
        if value is not None and name not in required
    ]
    if extra:
        raise ValueError(f"extra family parameter: {extra[0]}")
    return {name: float(parameters[name]) for name in required}


def evaluate(family: str, parameters: Mapping[str, float], x: np.ndarray) -> np.ndarray:
    """Evaluate one registered family on a finite grid."""

    if family == "constant":
        return np.full(x.shape, parameters["value"], dtype=float)
    if family == "linear":
        return parameters["slope"] * x + parameters["intercept"]
    if family == "quadratic":
        return (
            parameters["quadratic"] * x * x
            + parameters["slope"] * x
            + parameters["intercept"]
        )
    if family == "exponential_decay":
        with np.errstate(over="ignore", invalid="ignore"):
            return parameters["amplitude"] * np.exp(-parameters["rate"] * x) + parameters["offset"]
    raise ValueError(f"unknown model family: {family}")
