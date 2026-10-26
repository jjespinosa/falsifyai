"""Execution mode for parser and critic calls."""

from enum import Enum


class ExecutionMode(str, Enum):
    """Stub is the default. Live never falls back to stub."""

    STUB = "stub"
    LIVE = "live"
