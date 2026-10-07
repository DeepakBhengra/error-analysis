"""Vendored modules on PYTHONPATH satisfy the server start import check."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_start_server_uses_vendor_without_venv(tmp_path: Path, monkeypatch):
    root = tmp_path / "error-analysis-server"
    (root / "web" / "dist").mkdir(parents=True)
    (root / "web" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / ".env").write_text("DD_API_KEY=x\nDD_APP_KEY=y\n", encoding="utf-8")
    (root / "src").mkdir()
    vendor = root / "vendor"
    vendor.mkdir()
    (vendor / "fastapi.py").write_text("ok = True\n", encoding="utf-8")
    (vendor / "uvicorn.py").write_text("ok = True\n", encoding="utf-8")
    (vendor / "httpx.py").write_text("ok = True\n", encoding="utf-8")

    repo_script = Path(__file__).resolve().parents[1] / "start-server.sh"
    script = repo_script.read_text(encoding="utf-8")
    # Stop after the import check by replacing exec with a print.
    script = script.replace(
        'echo "Starting Error Analysis on http://${HOST}:${PORT}"\n'
        'exec "$PYTHON" -m uvicorn error_analysis.api:app --host "$HOST" --port "$PORT"\n',
        'echo "imports-ok"\nexit 0\n',
    )
    starter = root / "start-server.sh"
    starter.write_text(script, encoding="utf-8")
    starter.chmod(0o755)

    env = os.environ.copy()
    env["ERROR_ANALYSIS_HOST"] = "0.0.0.0"
    env["ERROR_ANALYSIS_PORT"] = "9000"
    result = subprocess.run(
        ["bash", str(starter)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "imports-ok" in result.stdout
    assert "venv" not in result.stdout.lower()


def test_start_laptop_defaults_to_localhost(tmp_path: Path):
    root = tmp_path / "error-analysis-server"
    root.mkdir()
    (root / "start-server.sh").write_text(
        "#!/usr/bin/env bash\n"
        "echo host=$ERROR_ANALYSIS_HOST port=$ERROR_ANALYSIS_PORT\n",
        encoding="utf-8",
    )
    (root / "start-server.sh").chmod(0o755)
    repo_script = Path(__file__).resolve().parents[1] / "start-laptop.sh"
    starter = root / "start-laptop.sh"
    starter.write_text(repo_script.read_text(encoding="utf-8"), encoding="utf-8")
    starter.chmod(0o755)
    env = os.environ.copy()
    env.pop("ERROR_ANALYSIS_HOST", None)
    env.pop("ERROR_ANALYSIS_PORT", None)
    result = subprocess.run(
        ["bash", str(starter)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "host=127.0.0.1" in result.stdout
    assert "port=8010" in result.stdout
