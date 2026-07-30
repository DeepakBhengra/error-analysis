from pathlib import Path

from error_analysis.env_file import upsert_env_values


def test_upsert_env_values_preserves_comments_and_other_keys(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nDD_API_KEY=old\nOTHER=keep\nORDER_CREATE_USERNAME=u1\n",
        encoding="utf-8",
    )
    upsert_env_values(
        {
            "DD_API_KEY": "new-key",
            "DEFAULT_ORDER_CREATE_TARGET": "qa",
            "ORDER_CREATE_USERNAME": "u2",
        },
        path=path,
    )
    text = path.read_text(encoding="utf-8")
    assert "# comment" in text
    assert "DD_API_KEY=new-key" in text
    assert "OTHER=keep" in text
    assert "ORDER_CREATE_USERNAME=u2" in text
    assert "DEFAULT_ORDER_CREATE_TARGET=qa" in text


def test_upsert_ignores_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("DD_API_KEY=a\n", encoding="utf-8")
    upsert_env_values({"NOT_ALLOWED": "x", "DD_APP_KEY": "b"}, path=path)
    text = path.read_text(encoding="utf-8")
    assert "NOT_ALLOWED" not in text
    assert "DD_APP_KEY=b" in text
