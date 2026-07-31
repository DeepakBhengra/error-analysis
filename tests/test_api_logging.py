"""API tests that runtime failures are written to application logs."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import error_analysis.logging_config as logging_config
from error_analysis.datadog.fetch_request import FetchRequestResult


@pytest.fixture
def logged_api(monkeypatch, tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DD_API_KEY=test-dd-api\n"
        "DD_APP_KEY=test-dd-app\n"
        "DD_SITE=us5.datadoghq.com\n"
        "ORDER_CREATE_USERNAME=user1\n"
        "ORDER_CREATE_PASSWORD=secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("error_analysis.env_file.ENV_PATH", env_path)
    for key in (
        "DD_API_KEY",
        "DD_APP_KEY",
        "DD_SITE",
        "ORDER_CREATE_USERNAME",
        "ORDER_CREATE_PASSWORD",
        "ORDER_CREATE_COOKIE",
    ):
        monkeypatch.delenv(key, raising=False)

    log_dir = tmp_path / "logs"
    monkeypatch.setenv("ERROR_ANALYSIS_LOG_DIR", str(log_dir))
    monkeypatch.setenv("ERROR_ANALYSIS_LOG_LEVEL", "INFO")

    root = logging.getLogger(logging_config.LOGGER_NAME)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    logging_config._configured = False

    from error_analysis.api import app

    with TestClient(app) as client:
        yield client, log_dir

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    logging_config._configured = False


def test_api_errors_are_written_to_error_log(logged_api, monkeypatch):
    client, log_dir = logged_api

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("error_analysis.api.DatadogClient", lambda settings: FakeClient())
    monkeypatch.setattr(
        "error_analysis.api.fetch_request_records",
        lambda *args, **kwargs: FetchRequestResult(
            records=[{"id": "1"}],
            query="q",
            total_logs=1,
            missing_payload=0,
            request_count=1,
            response_count=0,
        ),
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated replay crash")

    monkeypatch.setattr("error_analysis.api.run_replay", boom)

    res = client.post("/api/run", json={"text": "ORDER1"})
    assert res.status_code == 500

    for handler in logging.getLogger(logging_config.LOGGER_NAME).handlers:
        handler.flush()

    error_log = log_dir / "error-analysis-errors.log"
    assert error_log.is_file()
    text = error_log.read_text(encoding="utf-8")
    assert "simulated replay crash" in text
    assert "run replay failed" in text
