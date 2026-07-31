"""Tests for application logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import error_analysis.logging_config as logging_config
from error_analysis.logging_config import get_logger, setup_logging


@pytest.fixture(autouse=True)
def reset_logging_state():
    """Ensure each test starts with a clean logging configuration."""
    root = logging.getLogger(logging_config.LOGGER_NAME)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    logging_config._configured = False
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    logging_config._configured = False


def test_setup_logging_creates_log_files(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ERROR_ANALYSIS_LOG_DIR", raising=False)
    monkeypatch.delenv("ERROR_ANALYSIS_LOG_LEVEL", raising=False)

    log_dir = setup_logging(log_dir=tmp_path / "logs", level="INFO", force=True)
    assert log_dir == (tmp_path / "logs").resolve()

    logger = get_logger("test")
    logger.info("hello info")
    logger.error("hello error")

    for handler in logging.getLogger(logging_config.LOGGER_NAME).handlers:
        handler.flush()

    app_log = log_dir / "error-analysis.log"
    error_log = log_dir / "error-analysis-errors.log"
    assert app_log.is_file()
    assert error_log.is_file()

    app_text = app_log.read_text(encoding="utf-8")
    error_text = error_log.read_text(encoding="utf-8")
    assert "hello info" in app_text
    assert "hello error" in app_text
    assert "hello info" not in error_text
    assert "hello error" in error_text


def test_setup_logging_respects_env_dir_and_level(tmp_path: Path, monkeypatch):
    target = tmp_path / "custom-logs"
    monkeypatch.setenv("ERROR_ANALYSIS_LOG_DIR", str(target))
    monkeypatch.setenv("ERROR_ANALYSIS_LOG_LEVEL", "WARNING")

    log_dir = setup_logging(force=True)
    assert log_dir == target.resolve()

    logger = get_logger("env")
    logger.info("should be filtered")
    logger.warning("should appear")

    for handler in logging.getLogger(logging_config.LOGGER_NAME).handlers:
        handler.flush()

    text = (log_dir / "error-analysis.log").read_text(encoding="utf-8")
    assert "should be filtered" not in text
    assert "should appear" in text


def test_get_logger_namespaces_under_package():
    assert get_logger("api").name == "error_analysis.api"
    assert get_logger("error_analysis.cli").name == "error_analysis.cli"
    assert get_logger().name == "error_analysis"
