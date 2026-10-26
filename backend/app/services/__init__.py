"""M1 scientific services."""

from app.services.critic import critique_hypothesis
from app.services.modes import ExecutionMode
from app.services.parser import parse_hypothesis

__all__ = ["ExecutionMode", "critique_hypothesis", "parse_hypothesis"]
