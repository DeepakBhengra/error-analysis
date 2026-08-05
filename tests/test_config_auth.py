"""Tests for Datadog credential requirements on Settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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


def test_settings_reject_missing_datadog_auth():
    with pytest.raises(ValidationError, match="DD_ACCESS_TOKEN"):
        Settings(DD_SITE="us5.datadoghq.com")
