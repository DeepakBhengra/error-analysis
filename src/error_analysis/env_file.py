"""Read/write helpers for the project ``.env`` file."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

# Keys the Settings UI is allowed to update.
SETTINGS_ENV_KEYS = frozenset(
    {
        "DD_API_KEY",
        "DD_APP_KEY",
        "DD_ACCESS_TOKEN",
        "DD_SITE",
        "ORDER_CREATE_USERNAME",
        "ORDER_CREATE_PASSWORD",
        "ORDER_CREATE_COOKIE",
        "DEFAULT_ORDER_CREATE_TARGET",
        "DEFAULT_REPLAY_MODE",
    }
)


def env_file_path() -> Path:
    return ENV_PATH


def _format_env_value(value: str) -> str:
    if value == "":
        return ""
    needs_quotes = any(ch in value for ch in ' \t\n#"\'\\') or value.startswith("#")
    if not needs_quotes:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def upsert_env_values(updates: dict[str, str], *, path: Path | None = None) -> Path:
    """Upsert known keys in ``.env``, preserving other lines and comments.

    Creates the file if missing. Only keys in ``SETTINGS_ENV_KEYS`` are written.
    """
    target = path or ENV_PATH
    filtered = {k: v for k, v in updates.items() if k in SETTINGS_ENV_KEYS}
    if not filtered:
        return target

    lines: list[str] = []
    if target.is_file():
        lines = target.read_text(encoding="utf-8").splitlines()

    remaining = dict(filtered)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _, _rest = stripped.partition("=")
        key = key.strip()
        if key in remaining:
            new_lines.append(f"{key}={_format_env_value(remaining.pop(key))}")
        else:
            new_lines.append(line)

    if remaining:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        for key, value in remaining.items():
            new_lines.append(f"{key}={_format_env_value(value)}")

    text = "\n".join(new_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
