from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from error_analysis.config import Settings
from error_analysis.error_lookup.client import ErrorLookupError, lookup_error_code


def default_results_dir() -> Path:
    """Repo-root ``results/`` (…/Error_analsysis/results)."""
    # resolve.py → error_lookup → error_analysis → src → repo root
    return Path(__file__).resolve().parents[3] / "results"


def business_logic_filename(error_code: str) -> str:
    code = error_code.strip().upper()
    return f"{code} Business Logic.json"


def business_logic_path(error_code: str, results_dir: Path | None = None) -> Path:
    root = results_dir if results_dir is not None else default_results_dir()
    return root / business_logic_filename(error_code)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def resolve_error_code(
    settings: Settings,
    error_code: str,
    *,
    results_dir: Path | None = None,
) -> dict[str, Any]:
    """Lookup error code and persist under results/, or return cached file.

    Returns ``{"cached": bool, "path": str, "result": dict}``.
    """
    code = error_code.strip().upper()
    if not code:
        raise ErrorLookupError("error_code is required")

    path = business_logic_path(code, results_dir=results_dir)
    if path.is_file():
        cached = json.loads(path.read_text(encoding="utf-8"))
        return {
            "cached": True,
            "path": str(path),
            "result": cached,
        }

    result = lookup_error_code(settings, code)
    _write_json(path, result)
    return {
        "cached": False,
        "path": str(path),
        "result": result,
    }
