from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from error_analysis.env_file import env_file_path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Classic Datadog auth (API key + Application key).
    dd_api_key: str = Field(default="", alias="DD_API_KEY")
    dd_app_key: str = Field(default="", alias="DD_APP_KEY")
    # Personal / Service Access Token (Bearer). Preferred when set.
    dd_access_token: str = Field(default="", alias="DD_ACCESS_TOKEN")
    dd_site: str = Field(default="us5.datadoghq.com", alias="DD_SITE")

    default_query: str = Field(default='"G0D82"', alias="DEFAULT_QUERY")
    default_storage_tier: str = Field(default="indexes", alias="DEFAULT_STORAGE_TIER")
    default_sort: str = Field(default="-timestamp", alias="DEFAULT_SORT")
    default_page_limit: int = Field(default=50, alias="DEFAULT_PAGE_LIMIT")
    checkout_service: str = Field(
        default="AsyncOrderCreate,OrderCreate_v6*,OrderCreate_v2*",
        alias="CHECKOUT_SERVICE",
    )
    order_create_services: str = Field(
        default="AsyncOrderCreate,OrderCreate_v6*,OrderCreate_v2*",
        alias="ORDER_CREATE_SERVICES",
    )
    async_order_hosts: str = Field(
        default="uschileai1401,uschileai1402,uschileai1403,uschileai1404",
        alias="ASYNC_ORDER_HOSTS",
    )

    order_create_username: str = Field(default="", alias="ORDER_CREATE_USERNAME")
    order_create_password: str = Field(default="", alias="ORDER_CREATE_PASSWORD")
    order_create_cookie: str = Field(default="", alias="ORDER_CREATE_COOKIE")

    order_modify_test_username: str = Field(
        default="", alias="ORDER_MODIFY_TEST_USERNAME"
    )
    order_modify_test_password: str = Field(
        default="", alias="ORDER_MODIFY_TEST_PASSWORD"
    )
    order_modify_qa1_username: str = Field(default="", alias="ORDER_MODIFY_QA1_USERNAME")
    order_modify_qa1_password: str = Field(default="", alias="ORDER_MODIFY_QA1_PASSWORD")
    order_modify_services: str = Field(
        default="OrderModify_v6*",
        alias="ORDER_MODIFY_SERVICES",
    )

    default_order_create_target: str = Field(default="uat", alias="DEFAULT_ORDER_CREATE_TARGET")
    default_order_modify_target: str = Field(default="test", alias="DEFAULT_ORDER_MODIFY_TARGET")
    default_replay_mode: str = Field(default="one_up", alias="DEFAULT_REPLAY_MODE")

    # Inbound API key for POST /api/v1/order-curl (never expose in responses).
    order_curl_api_key: str = Field(default="", alias="ORDER_CURL_API_KEY")

    lookup_api_url: str = Field(
        default="http://127.0.0.1:8000/api/v1/lookup",
        alias="LOOKUP_API_URL",
    )
    lookup_api_key: str = Field(default="cobolilapp", alias="LOOKUP_API_KEY")
    lookup_application_key: str = Field(
        default="deepakcobolil88206",
        alias="LOOKUP_APPLICATION_KEY",
    )
    lookup_source_root: str = Field(
        default="C:/Legacy-Error-Code-Mapper-ver1/samples",
        alias="LOOKUP_SOURCE_ROOT",
    )
    lookup_rules_path: str = Field(
        default="C:/Legacy-Error-Code-Mapper-ver1/config/error_rules.json",
        alias="LOOKUP_RULES_PATH",
    )
    lookup_corora_mappings: str = Field(
        default="C:/Legacy-Error-Code-Mapper-ver1/error_mapping_files",
        alias="LOOKUP_CORORA_MAPPINGS",
    )

    @model_validator(mode="after")
    def require_datadog_credentials(self) -> "Settings":
        if self.dd_access_token.strip():
            return self
        if self.dd_api_key.strip() and self.dd_app_key.strip():
            return self
        raise ValueError(
            "Datadog auth required: set DD_ACCESS_TOKEN (Personal/Service Access Token), "
            "or both DD_API_KEY and DD_APP_KEY."
        )

    @property
    def uses_access_token(self) -> bool:
        return bool(self.dd_access_token.strip())

    @property
    def default_services(self) -> list[str]:
        raw = self.order_create_services or self.checkout_service
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def default_async_order_hosts(self) -> list[str]:
        return [part.strip() for part in self.async_order_hosts.split(",") if part.strip()]

    @property
    def default_modify_services(self) -> list[str]:
        return [part.strip() for part in self.order_modify_services.split(",") if part.strip()]

    @property
    def api_base_url(self) -> str:
        site = self.dd_site.removeprefix("https://").removeprefix("http://").rstrip("/")
        return f"https://api.{site}/"


def get_settings() -> Settings:
    return Settings(_env_file=env_file_path())
