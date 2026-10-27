"""Serve the built React app without taking API routes.

Development keeps using Vite. This module is used when FALSIFY_STATIC_DIR
points at a production frontend/dist.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, directory: Path | None) -> None:
    """Mount a built SPA. Missing directories leave the API unchanged."""

    if directory is None:
        return
    root = directory.resolve()
    index = root / "index.html"
    if not index.is_file():
        return
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if _reserved(full_path):
            raise HTTPException(status_code=404)
        candidate = _safe_file(root, full_path)
        if candidate is not None:
            return FileResponse(candidate)
        return FileResponse(index)


def _reserved(full_path: str) -> bool:
    head = full_path.split("/", 1)[0]
    return head in {"api", "docs", "redoc", "openapi.json"}


def _safe_file(root: Path, full_path: str) -> Path | None:
    if not full_path or full_path.endswith("/"):
        return None
    candidate = (root / full_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None
