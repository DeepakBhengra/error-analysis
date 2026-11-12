"""Tests for Datadog credential requirements on Settings."""

from __future__ import annotations

import pytest

from error_analysis.config import Settings


def test_settings_accept_access_token_alone():
    settings = Settings(DD_ACCESS_TOKEN="token-only", DD_SITE="us5.datadoghq.com")
    assert settings.uses_access_token is True
    assert settings.dd_api_key == ""


def test_settings_accept_api_and_app_keys():
    settings = Settings(
        DD_API_KEY="api",
        DD_APP_KEY="app",
        DD_SITE="us5.datadoghq.com",
    )
    assert settings.uses_access_token is False


def test_settings_allow_missing_datadog_auth_for_settings_ui():
    settings = Settings(DD_SITE="us5.datadoghq.com")
    assert settings.has_datadog_credentials is False
    assert settings.uses_access_token is False
    with pytest.raises(ValueError, match="DD_ACCESS_TOKEN"):
        settings.require_datadog_credentials()
