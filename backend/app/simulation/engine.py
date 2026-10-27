"""Deterministic local execution of a validated SimulationSpec."""

from __future__ import annotations

import numpy as np

from app.schemas.simulation import (
    ModelCurve,
    SimulationResult,
    SimulationResultMetadata,
    SimulationSpec,
)
from app.simulation.registry import active_parameters, evaluate


class SimulationRejected(ValueError):
    """The spec is declarative but its numerical result is not usable."""


def run_simulation(spec: SimulationSpec) -> SimulationResult:
    """Evaluate H0 and H1. This function does not call a language model."""

    if spec.template == "static_curve":
        grid = _linspace(
            spec.independent_variable.min,
            spec.independent_variable.max,
            spec.independent_variable.points,
        )
        h0 = _curve(spec.h0, grid)
        h1 = _curve(spec.h1, grid)
        x = grid
        points = spec.independent_variable.points
    else:
        if spec.sweep is None:
            raise SimulationRejected("parameter_sweep requires one sweep axis")
        anchor = _linspace(
            spec.independent_variable.min,
            spec.independent_variable.max,
            spec.independent_variable.points,
        )
        grid = _linspace(spec.sweep.min, spec.sweep.max, spec.sweep.points)
        h0_rows: list[float] = []
        h1_rows: list[float] = []
        h0_base = active_parameters(spec.h0.family, spec.h0.parameters.model_dump())
        h1_base = active_parameters(spec.h1.family, spec.h1.parameters.model_dump())
        for value in grid:
            h0_values = dict(h0_base)
            h1_values = dict(h1_base)
            if spec.sweep.target == "h0":
                h0_values[spec.sweep.parameter] = float(value)
            else:
                h1_values[spec.sweep.parameter] = float(value)
            h0_rows.append(float(_values(spec.h0.family, h0_values, anchor)[0]))
            h1_rows.append(float(_values(spec.h1.family, h1_values, anchor)[0]))
        x = grid
        h0 = np.asarray(h0_rows, dtype=float)
        h1 = np.asarray(h1_rows, dtype=float)
        points = spec.sweep.points
    delta = h1 - h0
    return SimulationResult(
        simulation_id=spec.simulation_id,
        observable_id=spec.observable_id,
        x=_finite_list(x),
        h0=_finite_list(h0),
        h1=_finite_list(h1),
        delta=_finite_list(delta),
        metadata=SimulationResultMetadata(
            template=spec.template,
            points=points,
            seed=spec.seed,
        ),
    )


def _curve(curve: ModelCurve, x: np.ndarray) -> np.ndarray:
    return _values(curve.family, active_parameters(curve.family, curve.parameters.model_dump()), x)


def _values(family: str, parameters: dict[str, float], x: np.ndarray) -> np.ndarray:
    try:
        return evaluate(family, parameters, x)
    except ValueError as exc:
        raise SimulationRejected(str(exc)) from None


def _linspace(lower: float, upper: float, points: int) -> np.ndarray:
    return np.linspace(lower, upper, points, dtype=float)


def _finite_list(values: np.ndarray) -> list[float]:
    if values.ndim != 1:
        raise SimulationRejected("numerical output must be one-dimensional")
    if not np.isfinite(values).all():
        raise SimulationRejected("numerical output must be finite")
    return [float(item) for item in values]
