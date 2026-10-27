"""Hard bounds for the restricted numerical simulator."""

MAX_GRID_POINTS = 1000
MAX_SWEEP_POINTS = 100
MAX_TOTAL_EVALUATIONS = 100_000
MAX_ABS_COORDINATE = 1_000_000.0


def require_evaluation_budget(grid_points: int, sweep_points: int) -> None:
    """Reject a grid or a one-parameter sweep that exceeds the fixed budget."""

    if grid_points < 1 or sweep_points < 1:
        raise ValueError("point counts must be positive")
    if grid_points * sweep_points > MAX_TOTAL_EVALUATIONS:
        raise ValueError("total evaluations exceed the configured maximum")
    if grid_points > MAX_GRID_POINTS:
        raise ValueError("grid point count exceeds the configured maximum")
    if sweep_points > MAX_SWEEP_POINTS:
        raise ValueError("sweep point count exceeds the configured maximum")
