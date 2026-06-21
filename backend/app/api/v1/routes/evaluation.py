"""
Evaluation results endpoint.

Serves the latest evaluation report (written by the scripts in `evaluation/`) to
the frontend Evaluation Dashboard. If no report exists yet, returns an empty
report rather than erroring so the dashboard renders cleanly on a fresh install.

Path resolution is deliberately forgiving. The report can live in several places
depending on how the backend is deployed:
  * Railway / a plain `docker build` bakes a copy into the image at
    `backend/evaluation/results/latest.json` (the root `.dockerignore` excludes
    the repo-root `evaluation/` dir, so the baked copy must live under `backend/`).
  * docker-compose bind-mounts the repo-root `evaluation/` over `/app/evaluation`
    and points `EVALUATION_RESULTS_PATH` at an absolute path inside it.
  * Local dev runs the offline harness, which writes to the repo-root
    `evaluation/results/latest.json` (i.e. one level above `backend/`).
`_resolve_report_path` tries each of these so the dashboard works in every mode
without per-environment configuration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.deps import get_current_principal
from app.auth.models import Principal
from app.core.config import BACKEND_DIR, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/evaluation", tags=["evaluation"])

_EMPTY = {
    "generated_at": None,
    "dataset": None,
    "summary": {},
    "samples": [],
    "available": False,
}

# Report baked into the image (shipped under backend/ so `COPY backend/ /app`
# includes it). Used as the last-resort fallback regardless of configuration.
_BAKED_REPORT = BACKEND_DIR / "evaluation" / "results" / "latest.json"


def _resolve_report_path() -> Optional[Path]:
    """Return the first existing candidate report path, or None.

    Order: the configured path (absolute, or resolved against the cwd, the
    backend dir, and the repo root), then the report baked into the image.
    """

    configured = Path(get_settings().evaluation_results_path)
    candidates: list[Path] = []
    if configured.is_absolute():
        candidates.append(configured)
    else:
        candidates.append((Path.cwd() / configured).resolve())
        candidates.append((BACKEND_DIR / configured).resolve())
        candidates.append((BACKEND_DIR.parent / configured).resolve())
    candidates.append(_BAKED_REPORT)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    logger.info("No evaluation report found; tried: %s", [str(c) for c in candidates])
    return None


@router.get("/results", summary="Latest evaluation report")
async def results(_: Principal = Depends(get_current_principal)) -> dict:
    path = _resolve_report_path()
    if path is None:
        return _EMPTY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["available"] = True
        logger.info("Serving evaluation report from %s", path)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read evaluation report at %s: %s", path, exc)
        return _EMPTY
