"""Application logging for Error Analysis.

Configures console output plus rotating log files under ``logs/`` so runtime
issues (API failures, Datadog errors, replay problems) are persisted for
diagnosis. Call :func:`setup_logging` once at process start (API lifespan or CLI).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from error_analysis.env_file import PROJECT_ROOT

DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_LOG_LEVEL = "INFO"
LOGGER_NAME = "error_analysis"

# Avoid attaching duplicate handlers when setup_logging is called more than once
# (tests, uvicorn reload parent/child, Typer callback + command).
_configured = False

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the ``error_analysis`` namespace."""
    if name is None or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def resolve_log_dir(log_dir: str | Path | None = None) -> Path:
    """Resolve the log directory from argument or ``ERROR_ANALYSIS_LOG_DIR``."""
    if log_dir is not None:
        return Path(log_dir).expanduser().resolve()
    env = (os.environ.get("ERROR_ANALYSIS_LOG_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_LOG_DIR.resolve()


def resolve_log_level(level: str | None = None) -> int:
    """Resolve a log level name from argument or ``ERROR_ANALYSIS_LOG_LEVEL``."""
    raw = (level or os.environ.get("ERROR_ANALYSIS_LOG_LEVEL") or DEFAULT_LOG_LEVEL).strip()
    resolved = logging.getLevelName(raw.upper())
    if isinstance(resolved, int):
        return resolved
    return logging.INFO


def setup_logging(
    *,
    level: str | None = None,
    log_dir: str | Path | None = None,
    force: bool = False,
) -> Path:
    """Configure package logging to console and rotating files.

    Creates ``<log_dir>/error-analysis.log`` (all levels) and
    ``<log_dir>/error-analysis-errors.log`` (WARNING and above).

    Returns the resolved log directory path.
    """
    global _configured

    target_dir = resolve_log_dir(log_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    log_level = resolve_log_level(level)
    root = logging.getLogger(LOGGER_NAME)

    if _configured and not force:
        root.setLevel(log_level)
        return target_dir

    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()

    root.setLevel(log_level)
    root.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Full application log (INFO+ by default, subject to root level).
    app_log = target_dir / "error-analysis.log"
    file_handler = RotatingFileHandler(
        app_log,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Dedicated error log for warnings and failures while the app is running.
    error_log = target_dir / "error-analysis-errors.log"
    error_handler = RotatingFileHandler(
        error_log,
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    _configured = True
    root.debug("Logging configured (level=%s, dir=%s)", logging.getLevelName(log_level), target_dir)
    return target_dir
