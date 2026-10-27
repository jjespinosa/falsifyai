"""Local numerical check for the registered families.

Run it explicitly:

    python scripts/local_m3_engine.py

This script does not read the API key and does not call the network.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Evaluate the synthetic quadratic fixture and print the comparison error."""

    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.services.m3_fixtures import synthetic_spec
    from app.simulation.engine import run_simulation

    result = run_simulation(synthetic_spec())
    expected = [0.1 * value * value for value in result.x]
    error = max(abs(left - right) for left, right in zip(result.delta, expected, strict=True))
    print(f"x_first: {result.x[0]}")
    print(f"x_last: {result.x[-1]}")
    print(f"points: {result.metadata.points}")
    print(f"h0_first: {result.h0[0]}")
    print(f"h0_last: {result.h0[-1]}")
    print(f"h1_first: {result.h1[0]}")
    print(f"h1_last: {result.h1[-1]}")
    print(f"delta_first: {result.delta[0]}")
    print(f"delta_last: {result.delta[-1]}")
    print(f"max_abs_error: {error}")
    print("model_api_calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
