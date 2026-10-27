"""Public-demo limits. They do not change a scientific verdict.

Stub runs stay available when live calls are turned off. A refused live call
does not fall back to the stub.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from app.config import Settings
from app.services.modes import ExecutionMode

PUBLIC_EFFORTS = frozenset({"minimal", "low", "medium"})


class LiveQuota:
    """A small in-memory cap. It is a demo control, not an account system."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        with self._lock:
            recent = self._hits.setdefault(key, deque())
            cutoff = moment - self.window_seconds
            while recent and recent[0] < cutoff:
                recent.popleft()
            if len(recent) >= self.limit:
                return False
            recent.append(moment)
            if len(self._hits) > 5_000:
                self._hits.pop(next(iter(self._hits)))
            return True


class BoundedBodyMiddleware:
    """Refuse a declared body larger than the demo limit."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            response = JSONResponse(
                {"detail": "request body exceeds the demo limit"},
                status_code=413,
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def enforce_release_limits(request: Request, mode: ExecutionMode, statement: str) -> None:
    """Apply length, live-switch, and per-client quota before any model call."""

    settings: Settings = request.app.state.settings
    if len(statement) > settings.max_hypothesis_length:
        raise HTTPException(status_code=422, detail="hypothesis exceeds the demo length limit")
    if mode is not ExecutionMode.LIVE:
        return
    if not settings.live_runs_enabled:
        raise HTTPException(
            status_code=403,
            detail="Live runs are disabled. Stub mode remains available.",
        )
    quota: LiveQuota = request.app.state.live_quota
    if not quota.allow(_client_key(request)):
        raise HTTPException(
            status_code=429,
            detail="This demo has reached its live-run limit. Stub mode remains available.",
        )


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return forwarded.split(",")[0].strip()[:200] or "unknown"
    client = request.client
    if client is None or not client.host:
        return "unknown"
    return client.host


def _content_length(scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
