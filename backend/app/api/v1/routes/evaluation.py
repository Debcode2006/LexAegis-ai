"""
Evaluation results endpoint.

Serves the latest evaluation report (written by the scripts in `evaluation/`) to
the frontend Evaluation Dashboard. If no report exists yet, returns an empty
report rather than erroring so the dashboard renders cleanly on a fresh install.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import get_current_principal
from app.auth.models import Principal
from app.core.config import get_settings
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


@router.get("/results", summary="Latest evaluation report")
async def results(_: Principal = Depends(get_current_principal)) -> dict:
    path = Path(get_settings().evaluation_results_path)
    if not path.is_absolute():
        # Resolve relative to the backend working directory.
        path = (Path.cwd() / path).resolve()
    if not path.exists():
        logger.info("No evaluation report at %s", path)
        return _EMPTY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["available"] = True
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read evaluation report: %s", exc)
        return _EMPTY
