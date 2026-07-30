import json
from pathlib import Path

from error_analysis.datadog.url_parser import parse_datadog_logs_url

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLE_URL = (
    "https://us5.datadoghq.com/logs?"
    "query=%22G0D82%22"
    "&agg_m=count"
    "&cols=host%2Cservice%2C%40http.requestheader"
    "&storage=hot"
    "&stream_sort=desc"
    "&from_ts=1780299883494"
    "&to_ts=1780300783494"
    "&live=true"
)


def test_parse_datadog_logs_url_query():
    parsed = parse_datadog_logs_url(SAMPLE_URL)
    assert parsed.query == '"G0D82"'


def test_parse_datadog_logs_url_timestamps():
    parsed = parse_datadog_logs_url(SAMPLE_URL)
    assert parsed.from_time == "2026-06-01T07:44:43.494Z"
    assert parsed.to_time == "2026-06-01T07:59:43.494Z"


def test_parse_datadog_logs_url_storage_and_sort():
    parsed = parse_datadog_logs_url(SAMPLE_URL)
    assert parsed.storage_tier == "indexes"
    assert parsed.sort == "-timestamp"


def test_parse_datadog_logs_url_display_fields():
    parsed = parse_datadog_logs_url(SAMPLE_URL)
    assert parsed.display_fields == ["host", "service", "@http.requestheader"]
