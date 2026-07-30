"""API tests for GET/PUT /api/settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def settings_env(monkeypatch, tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DD_API_KEY=test-dd-api\n"
        "DD_APP_KEY=test-dd-app\n"
        "DD_SITE=us5.datadoghq.com\n"
        "ORDER_CREATE_USERNAME=user1\n"
        "ORDER_CREATE_PASSWORD=secret\n"
        "DEFAULT_ORDER_CREATE_TARGET=uat\n"
        "DEFAULT_REPLAY_MODE=one_up\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("error_analysis.env_file.ENV_PATH", env_path)
    # Clear process overrides so Settings reads from the tmp .env file.
    for key in (
        "DD_API_KEY",
        "DD_APP_KEY",
        "DD_SITE",
        "ORDER_CREATE_USERNAME",
        "ORDER_CREATE_PASSWORD",
        "ORDER_CREATE_COOKIE",
        "DEFAULT_ORDER_CREATE_TARGET",
        "DEFAULT_REPLAY_MODE",
    ):
        monkeypatch.delenv(key, raising=False)
    return env_path


def test_get_settings_masks_secrets(settings_env):
    from error_analysis.api import app

    client = TestClient(app)
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["dd_api_key"] == ""
    assert data["dd_app_key"] == ""
    assert data["order_create_password"] == ""
    assert data["dd_api_key_configured"] is True
    assert data["order_create_password_configured"] is True
    assert data["order_create_username"] == "user1"
    assert data["default_target"] == "uat"
    assert data["default_mode"] == "one_up"


def test_put_settings_updates_defaults_and_env(settings_env):
    from error_analysis.api import app

    client = TestClient(app)
    res = client.put(
        "/api/settings",
        json={
            "default_target": "qa",
            "default_mode": "random",
            "order_create_username": "user2",
            "dd_api_key": "new-api-key",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["default_target"] == "qa"
    assert data["default_mode"] == "random"
    assert data["order_create_username"] == "user2"
    assert data["dd_api_key_configured"] is True
    text = settings_env.read_text(encoding="utf-8")
    assert "DEFAULT_ORDER_CREATE_TARGET=qa" in text
    assert "DEFAULT_REPLAY_MODE=random" in text
    assert "ORDER_CREATE_USERNAME=user2" in text
    assert "DD_API_KEY=new-api-key" in text
    assert "ORDER_CREATE_PASSWORD=secret" in text
