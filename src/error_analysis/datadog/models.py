from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class LogSearchFilter(BaseModel):
    query: str
    from_time: str = Field(alias="from")
    to_time: str = Field(alias="to")
    storage_tier: str = "indexes"

    model_config = {"populate_by_name": True}

    def to_api_dict(self) -> dict[str, str]:
        return {
            "query": self.query,
            "from": self.from_time,
            "to": self.to_time,
            "storage_tier": self.storage_tier,
        }


class LogSearchParams(BaseModel):
    filter: LogSearchFilter
    sort: str = "-timestamp"
    page_limit: int = 50
    display_fields: list[str] = Field(default_factory=list)

    def to_api_body(self, cursor: str | None = None) -> dict[str, Any]:
        page: dict[str, Any] = {"limit": self.page_limit}
        if cursor:
            page["cursor"] = cursor

        return {
            "filter": self.filter.to_api_dict(),
            "sort": self.sort,
            "page": page,
        }


class ParsedDatadogUrl(BaseModel):
    query: str | None = None
    from_time: str | None = None
    to_time: str | None = None
    storage_tier: str = "indexes"
    sort: str = "-timestamp"
    display_fields: list[str] = Field(default_factory=list)


def ms_to_iso(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
