"""Bind host/port from ERROR_ANALYSIS_HOST / ERROR_ANALYSIS_PORT."""

from __future__ import annotations

import pytest

from error_analysis.api import DEFAULT_BIND_HOST, DEFAULT_BIND_PORT, bind_host, bind_port


def test_bind_defaults(monkeypatch):
    monkeypatch.delenv("ERROR_ANALYSIS_HOST", raising=False)
    monkeypatch.delenv("ERROR_ANALYSIS_PORT", raising=False)
    assert bind_host() == DEFAULT_BIND_HOST
    assert bind_port() == DEFAULT_BIND_PORT


def test_bind_from_env(monkeypatch):
    monkeypatch.setenv("ERROR_ANALYSIS_HOST", "0.0.0.0")
    monkeypatch.setenv("ERROR_ANALYSIS_PORT", "9000")
    assert bind_host() == "0.0.0.0"
    assert bind_port() == 9000


def test_bind_port_rejects_invalid(monkeypatch):
    monkeypatch.setenv("ERROR_ANALYSIS_PORT", "not-a-port")
    with pytest.raises(SystemExit):
        bind_port()
    monkeypatch.setenv("ERROR_ANALYSIS_PORT", "70000")
    with pytest.raises(SystemExit):
        bind_port()
